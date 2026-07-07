#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include <lc3.h>

#include <zephyr/audio/dmic.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/byteorder.h>

LOG_MODULE_REGISTER(xiao_ble_mic, LOG_LEVEL_INF);

#define DEVICE_NAME CONFIG_BT_DEVICE_NAME
#define DEVICE_NAME_LEN (sizeof(DEVICE_NAME) - 1)

#define SAMPLE_RATE_HZ 16000
#define CHANNELS 1
#define SAMPLE_BIT_WIDTH 16
#define BYTES_PER_SAMPLE 2
#define LC3_FRAME_US 10000
#define LC3_BITRATE_BPS 32000
#define LC3_FRAME_SAMPLES 160
#define LC3_FRAME_BYTES 40
#define APP_HEADER_SIZE 6
#define LC3_PACKET_SIZE (APP_HEADER_SIZE + LC3_FRAME_BYTES)
#define READ_TIMEOUT_MS 100
#define AUDIO_BLOCK_SIZE (LC3_FRAME_SAMPLES * BYTES_PER_SAMPLE)
#define AUDIO_BLOCK_COUNT 12
#define PDM_CONTROLLER_INDEX 0
#define PDM_POWER_NODE DT_ALIAS(pdm_power)

K_MEM_SLAB_DEFINE_STATIC(audio_slab, AUDIO_BLOCK_SIZE, AUDIO_BLOCK_COUNT, 4);

static const struct device *const dmic_dev = DEVICE_DT_GET(DT_NODELABEL(dmic_dev));

#if DT_NODE_EXISTS(PDM_POWER_NODE)
static const struct gpio_dt_spec pdm_power = GPIO_DT_SPEC_GET(PDM_POWER_NODE, gpios);
#endif

static struct bt_conn *current_conn;
static volatile bool notify_enabled;
static volatile bool stream_requested;
static uint16_t tx_seq;
static uint8_t tx_packet[LC3_PACKET_SIZE];
static uint32_t notify_drop_count;
static uint32_t notify_ok_count;
static uint32_t encode_fail_count;
static lc3_encoder_mem_16k_t lc3_encoder_mem;
static lc3_encoder_t lc3_encoder;

static void advertise(void);
static void advertise_work_handler(struct k_work *work);
K_WORK_DELAYABLE_DEFINE(advertise_work, advertise_work_handler);

static struct bt_uuid_128 audio_service_uuid =
	BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x04a77077, 0x8d9a, 0x4cd2, 0xbf83,
					    0xf7adafa02251));
static struct bt_uuid_128 audio_char_uuid =
	BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30fafbf6, 0x9ec3, 0x41ae, 0x86b9,
					    0x60cbf31328bb));

static void ccc_cfg_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
	ARG_UNUSED(attr);
	notify_enabled = (value == BT_GATT_CCC_NOTIFY);
	stream_requested = notify_enabled;
	LOG_INF("LC3 notifications %s", notify_enabled ? "enabled" : "disabled");
	if (notify_enabled) {
		tx_seq = 0;
		notify_drop_count = 0;
		notify_ok_count = 0;
		encode_fail_count = 0;
	}
}

BT_GATT_SERVICE_DEFINE(audio_svc,
	BT_GATT_PRIMARY_SERVICE(&audio_service_uuid),
	BT_GATT_CHARACTERISTIC(&audio_char_uuid.uuid, BT_GATT_CHRC_NOTIFY,
			       BT_GATT_PERM_NONE, NULL, NULL, NULL),
	BT_GATT_CCC(ccc_cfg_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE)
);

static const uint8_t audio_service_uuid_ad[] = {
	BT_UUID_128_ENCODE(0x04a77077, 0x8d9a, 0x4cd2, 0xbf83, 0xf7adafa02251),
};
static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA(BT_DATA_UUID128_ALL, audio_service_uuid_ad, sizeof(audio_service_uuid_ad)),
};
static const struct bt_data sd[] = {
	BT_DATA(BT_DATA_NAME_COMPLETE, DEVICE_NAME, DEVICE_NAME_LEN),
};

static void request_link_updates(struct bt_conn *conn)
{
	const struct bt_conn_le_data_len_param data_len = {
		.tx_max_len = BT_GAP_DATA_LEN_MAX,
		.tx_max_time = BT_GAP_DATA_TIME_MAX,
	};
	int err = bt_conn_le_param_update(conn, BT_LE_CONN_PARAM(12, 24, 0, 400));
	if (err) { LOG_WRN("Connection parameter update failed: %d", err); }
	err = bt_conn_le_phy_update(conn, BT_CONN_LE_PHY_PARAM_2M);
	if (err) { LOG_WRN("2M PHY update failed: %d", err); }
	err = bt_conn_le_data_len_update(conn, &data_len);
	if (err) { LOG_WRN("Data length update failed: %d", err); }
}

static void connected(struct bt_conn *conn, uint8_t err)
{
	char addr[BT_ADDR_LE_STR_LEN];
	bt_addr_le_to_str(bt_conn_get_dst(conn), addr, sizeof(addr));
	if (err) {
		LOG_ERR("Connection from %s failed: 0x%02x", addr, err);
		return;
	}
	current_conn = bt_conn_ref(conn);
	notify_enabled = false;
	stream_requested = false;
	tx_seq = 0;
	notify_drop_count = 0;
	notify_ok_count = 0;
	encode_fail_count = 0;
	k_work_cancel_delayable(&advertise_work);
	LOG_INF("Connected: %s", addr);
	request_link_updates(conn);
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	char addr[BT_ADDR_LE_STR_LEN];
	bt_addr_le_to_str(bt_conn_get_dst(conn), addr, sizeof(addr));
	LOG_INF("Disconnected: %s, reason 0x%02x", addr, reason);
	notify_enabled = false;
	stream_requested = false;
	if (current_conn) {
		bt_conn_unref(current_conn);
		current_conn = NULL;
	}
	k_work_reschedule(&advertise_work, K_MSEC(500));
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
	.connected = connected,
	.disconnected = disconnected,
};

static void advertise(void)
{
	int err = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, ad, ARRAY_SIZE(ad), sd, ARRAY_SIZE(sd));
	if (err == -EALREADY) { return; }
	if (err) {
		LOG_ERR("Advertising failed: %d", err);
		k_work_reschedule(&advertise_work, K_SECONDS(1));
		return;
	}
	LOG_INF("Advertising as %s", DEVICE_NAME);
}

static void advertise_work_handler(struct k_work *work)
{
	ARG_UNUSED(work);
	advertise();
}

static int configure_lc3(void)
{
	int expected_bytes = lc3_frame_bytes(LC3_FRAME_US, LC3_BITRATE_BPS);
	if (expected_bytes != LC3_FRAME_BYTES) {
		LOG_WRN("LC3 frame bytes expected %d, using %d", expected_bytes, LC3_FRAME_BYTES);
	}
	lc3_encoder = lc3_setup_encoder(LC3_FRAME_US, SAMPLE_RATE_HZ, 0, &lc3_encoder_mem);
	if (!lc3_encoder) {
		LOG_ERR("LC3 encoder setup failed");
		return -EINVAL;
	}
	lc3_encoder_disable_ltpf(lc3_encoder);
	return 0;
}

static int send_lc3_frame(const int16_t *samples, size_t sample_count)
{
	int err;
	if (!current_conn || !notify_enabled || sample_count < LC3_FRAME_SAMPLES) {
		return 0;
	}
	err = lc3_encode(lc3_encoder, LC3_PCM_FORMAT_S16, samples, 1,
			 LC3_FRAME_BYTES, &tx_packet[APP_HEADER_SIZE]);
	if (err) {
		encode_fail_count++;
		if ((encode_fail_count % 25U) == 1U) {
			LOG_WRN("LC3 encode failures=%u err=%d", encode_fail_count, err);
		}
		return err;
	}
	sys_put_le16(tx_seq, tx_packet);
	sys_put_le16(LC3_FRAME_SAMPLES, &tx_packet[2]);
	sys_put_le16(LC3_FRAME_BYTES, &tx_packet[4]);
	err = bt_gatt_notify(current_conn, &audio_svc.attrs[2], tx_packet, sizeof(tx_packet));
	if (err) {
		notify_drop_count++;
		if (err == -ENOTCONN) {
			notify_enabled = false;
			stream_requested = false;
		}
		if ((notify_drop_count % 25U) == 1U) {
			LOG_WRN("Dropped LC3 packets=%u ok=%u latest_seq=%u err=%d",
				notify_drop_count, notify_ok_count, tx_seq, err);
		}
		return err;
	}
	tx_seq++;
	notify_ok_count++;
	return 0;
}

static int configure_pdm(void)
{
	struct pcm_stream_cfg stream = {
		.pcm_width = SAMPLE_BIT_WIDTH,
		.pcm_rate = SAMPLE_RATE_HZ,
		.block_size = AUDIO_BLOCK_SIZE,
		.mem_slab = &audio_slab,
	};
	struct dmic_cfg cfg = {
		.io = {
			.min_pdm_clk_freq = 1000000,
			.max_pdm_clk_freq = 3500000,
			.min_pdm_clk_dc = 40,
			.max_pdm_clk_dc = 60,
		},
		.streams = &stream,
		.channel = {
			.req_num_streams = 1,
			.req_num_chan = CHANNELS,
			.req_chan_map_lo = dmic_build_channel_map(0, PDM_CONTROLLER_INDEX, PDM_CHAN_LEFT),
		},
	};
	return dmic_configure(dmic_dev, &cfg);
}

static int enable_pdm_power(void)
{
#if DT_NODE_EXISTS(PDM_POWER_NODE)
	int err;
	if (!gpio_is_ready_dt(&pdm_power)) { return -ENODEV; }
	err = gpio_pin_configure_dt(&pdm_power, GPIO_OUTPUT_ACTIVE);
	if (err) { return err; }
	k_sleep(K_MSEC(10));
#endif
	return 0;
}

int main(void)
{
	int err;
	bool stream_active = false;
	LOG_INF("Starting LC3 BLE microphone stream: %d Hz, %d bytes/frame", SAMPLE_RATE_HZ, LC3_FRAME_BYTES);
	err = enable_pdm_power();
	if (err) { return 0; }
	if (!device_is_ready(dmic_dev)) {
		LOG_ERR("%s is not ready", dmic_dev->name);
		return 0;
	}
	err = configure_lc3();
	if (err) { return 0; }
	err = configure_pdm();
	if (err) {
		LOG_ERR("PDM configure failed: %d", err);
		return 0;
	}
	err = bt_enable(NULL);
	if (err) {
		LOG_ERR("Bluetooth init failed: %d", err);
		return 0;
	}
	advertise();
	while (true) {
		void *buffer;
		size_t size;
		if (!stream_requested) {
			if (stream_active) {
				err = dmic_trigger(dmic_dev, DMIC_TRIGGER_STOP);
				if (err) { LOG_WRN("PDM stop failed: %d", err); }
				stream_active = false;
				LOG_INF("PDM stopped");
			}
			k_sleep(K_MSEC(50));
			continue;
		}
		if (!stream_active) {
			err = dmic_trigger(dmic_dev, DMIC_TRIGGER_START);
			if (err) {
				LOG_ERR("PDM start failed: %d", err);
				stream_requested = false;
				notify_enabled = false;
				k_sleep(K_MSEC(250));
				continue;
			}
			stream_active = true;
			LOG_INF("PDM started");
		}
		err = dmic_read(dmic_dev, 0, &buffer, &size, READ_TIMEOUT_MS);
		if (err) {
			if (err != -EAGAIN) { LOG_WRN("PDM read failed: %d", err); }
			continue;
		}
		if (notify_enabled) {
			(void)send_lc3_frame((const int16_t *)buffer, size / BYTES_PER_SAMPLE);
		}
		k_mem_slab_free(&audio_slab, buffer);
	}
}

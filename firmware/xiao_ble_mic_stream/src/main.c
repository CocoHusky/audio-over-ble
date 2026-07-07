#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

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
#define FRAME_SAMPLES 160
#define FRAME_US 10000
#define APP_HEADER_SIZE 6
#define ADPCM_STATE_BYTES 4
#define ADPCM_NIBBLE_BYTES 80
#define ADPCM_FRAME_BYTES (ADPCM_STATE_BYTES + ADPCM_NIBBLE_BYTES)
#define AUDIO_PACKET_SIZE (APP_HEADER_SIZE + ADPCM_FRAME_BYTES)
#define READ_TIMEOUT_MS 100
#define AUDIO_BLOCK_SIZE (FRAME_SAMPLES * BYTES_PER_SAMPLE)
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
static uint8_t tx_packet[AUDIO_PACKET_SIZE];
static uint32_t notify_drop_count;
static uint32_t notify_ok_count;
static uint8_t adpcm_index_state;

static const int ima_step_table[89] = {
	7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
	19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
	50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
	130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
	337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
	876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
	2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
	5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
	15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
};

static const int ima_index_table[16] = {
	-1, -1, -1, -1, 2, 4, 6, 8,
	-1, -1, -1, -1, 2, 4, 6, 8,
};

static void advertise(void);
static void advertise_work_handler(struct k_work *work);
K_WORK_DELAYABLE_DEFINE(advertise_work, advertise_work_handler);

static struct bt_uuid_128 audio_service_uuid =
	BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x04a77077, 0x8d9a, 0x4cd2, 0xbf83,
					    0xf7adafa02251));
static struct bt_uuid_128 audio_char_uuid =
	BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30fafbf6, 0x9ec3, 0x41ae, 0x86b9,
					    0x60cbf31328bb));

static int clamp_int(int value, int min_value, int max_value)
{
	if (value < min_value) {
		return min_value;
	}
	if (value > max_value) {
		return max_value;
	}
	return value;
}

static uint8_t ima_encode_sample(int sample, int *predictor, uint8_t *index)
{
	int step = ima_step_table[*index];
	int diff = sample - *predictor;
	uint8_t nibble = 0;
	int vpdiff = step >> 3;

	if (diff < 0) {
		nibble = 8;
		diff = -diff;
	}

	if (diff >= step) {
		nibble |= 4;
		diff -= step;
		vpdiff += step;
	}
	if (diff >= (step >> 1)) {
		nibble |= 2;
		diff -= step >> 1;
		vpdiff += step >> 1;
	}
	if (diff >= (step >> 2)) {
		nibble |= 1;
		vpdiff += step >> 2;
	}

	if (nibble & 8) {
		*predictor -= vpdiff;
	} else {
		*predictor += vpdiff;
	}
	*predictor = clamp_int(*predictor, INT16_MIN, INT16_MAX);
	*index = (uint8_t)clamp_int((int)*index + ima_index_table[nibble], 0, 88);

	return nibble & 0x0f;
}

static int encode_adpcm_frame(const int16_t *samples, size_t sample_count,
			      uint8_t *payload, size_t payload_size)
{
	int predictor;
	uint8_t index;

	if (sample_count < FRAME_SAMPLES || payload_size < ADPCM_FRAME_BYTES) {
		return -EINVAL;
	}

	predictor = samples[0];
	index = adpcm_index_state;

	sys_put_le16((uint16_t)predictor, payload);
	payload[2] = index;
	payload[3] = 0;
	memset(&payload[ADPCM_STATE_BYTES], 0, ADPCM_NIBBLE_BYTES);

	for (size_t i = 1; i < FRAME_SAMPLES; i++) {
		uint8_t nibble = ima_encode_sample(samples[i], &predictor, &index);
		size_t encoded_i = i - 1;
		size_t byte_i = ADPCM_STATE_BYTES + (encoded_i >> 1);

		if (encoded_i & 1U) {
			payload[byte_i] |= (uint8_t)(nibble << 4);
		} else {
			payload[byte_i] = nibble;
		}
	}

	adpcm_index_state = index;
	return 0;
}

static void ccc_cfg_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
	ARG_UNUSED(attr);
	notify_enabled = (value == BT_GATT_CCC_NOTIFY);
	stream_requested = notify_enabled;
	LOG_INF("ADPCM notifications %s", notify_enabled ? "enabled" : "disabled");
	if (notify_enabled) {
		tx_seq = 0;
		notify_drop_count = 0;
		notify_ok_count = 0;
		adpcm_index_state = 0;
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
	adpcm_index_state = 0;
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

static int send_adpcm_frame(const int16_t *samples, size_t sample_count)
{
	int err;
	if (!current_conn || !notify_enabled || sample_count < FRAME_SAMPLES) {
		return 0;
	}

	err = encode_adpcm_frame(samples, sample_count, &tx_packet[APP_HEADER_SIZE], ADPCM_FRAME_BYTES);
	if (err) {
		return err;
	}

	sys_put_le16(tx_seq, tx_packet);
	sys_put_le16(FRAME_SAMPLES, &tx_packet[2]);
	sys_put_le16(ADPCM_FRAME_BYTES, &tx_packet[4]);
	err = bt_gatt_notify(current_conn, &audio_svc.attrs[2], tx_packet, sizeof(tx_packet));
	if (err) {
		notify_drop_count++;
		if (err == -ENOTCONN) {
			notify_enabled = false;
			stream_requested = false;
		}
		if ((notify_drop_count % 25U) == 1U) {
			LOG_WRN("Dropped ADPCM packets=%u ok=%u latest_seq=%u err=%d",
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
	LOG_INF("Starting ADPCM BLE microphone stream: %d Hz, %d bytes/frame", SAMPLE_RATE_HZ, ADPCM_FRAME_BYTES);
	err = enable_pdm_power();
	if (err) { return 0; }
	if (!device_is_ready(dmic_dev)) {
		LOG_ERR("%s is not ready", dmic_dev->name);
		return 0;
	}
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
			(void)send_adpcm_frame((const int16_t *)buffer, size / BYTES_PER_SAMPLE);
		}
		k_mem_slab_free(&audio_slab, buffer);
	}
}

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include "driver/i2s.h"
#include "esp_heap_caps.h"

const char WIFI_SSID[] = "YOUR_SSID";
const char WIFI_PASSWORD[] = "YOUR_PASSWORD";

const char BACKEND_HOST[] = "10.83.60.246";
const uint16_t BACKEND_PORT = 8000;

const char DEVICE_ID[] = "camcontroller";
const char DEVICE_TYPE[] = "esp32s3cam";
const char FIRMWARE_VERSION[] = "2.0.0";

const char WAKE_WORD[] = "HI CHETAN";

const int AUDIO_SAMPLE_RATE = 16000;
const int AUDIO_BITS_PER_SAMPLE = 16;
const int AUDIO_CHANNELS = 1;
const int RECORD_SECONDS = 20;

const int I2S_BCLK_PIN = 4;
const int I2S_LRC_PIN = 5;
const int I2S_DOUT_PIN = 6;
const int I2S_DIN_PIN = 7;

const int WAKE_FRAME_SAMPLES = 512;
const int WAKE_REQUIRED_FRAMES = 1;
const int WAKE_THRESHOLD_MIN = 150;
const int WAKE_MARGIN = 200;
const int WAKE_COOLDOWN_MS = 2000;

const i2s_port_t I2S_PORT = I2S_NUM_0;

enum SystemState {
  WIFI_CONNECTING,
  WIFI_CONNECTED,
  WS_CONNECTING,
  WS_CONNECTED
};

SystemState system_state = WIFI_CONNECTING;

bool audio_initialized = false;
bool audio_playing = false;
unsigned long last_playback_end = 0;
unsigned long audio_playing_start = 0;
const unsigned long AUDIO_PLAYING_TIMEOUT = 15000; // 15s max for any audio sequence
bool manual_record_requested = false;
bool prompt_waiting = false;

unsigned long last_heartbeat = 0;
const unsigned long HEARTBEAT_INTERVAL = 5000;
unsigned long last_wake_time = 0;
uint32_t last_wake_level = 0;
int wake_threshold = WAKE_THRESHOLD_MIN;

unsigned long last_ws_attempt = 0;
const unsigned long WS_RECONNECT_INTERVAL = 5000;

WebSocketsClient webSocket;

int base64_index(char c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  if (c == '+') return 62;
  if (c == '/') return 63;
  return -1;
}

size_t decode_base64(const char* input, uint8_t** output) {
  size_t len = strlen(input);
  int padding = 0;
  if (len >= 1 && input[len - 1] == '=') padding++;
  if (len >= 2 && input[len - 2] == '=') padding++;
  size_t out_len = (len * 3) / 4 - padding;
  *output = (uint8_t*)malloc(out_len);
  if (!*output) return 0;

  size_t out_index = 0;
  int i = 0;
  while (i < (int)len) {
    int vals[4];
    int vcount = 0;
    while (vcount < 4 && i < (int)len) {
      char c = input[i++];
      if (c == '\r' || c == '\n' || c == ' ') continue;
      if (c == '=') {
        vals[vcount++] = -2;
      } else {
        int idx = base64_index(c);
        if (idx < 0) continue;
        vals[vcount++] = idx;
      }
    }
    if (vcount < 4) break;
    if (vals[0] < 0 || vals[1] < 0) break;
    uint32_t triple = (vals[0] << 18) | (vals[1] << 12) | ((vals[2] < 0 ? 0 : vals[2]) << 6) | (vals[3] < 0 ? 0 : vals[3]);
    if (out_index < out_len) (*output)[out_index++] = (triple >> 16) & 0xFF;
    if (vals[2] >= 0 && out_index < out_len) (*output)[out_index++] = (triple >> 8) & 0xFF;
    if (vals[3] >= 0 && out_index < out_len) (*output)[out_index++] = triple & 0xFF;
  }
  return out_index;
}

String url_encode(const char* input) {
  String out;
  const char* hex = "0123456789ABCDEF";
  for (size_t i = 0; input[i] != '\0'; i++) {
    char c = input[i];
    if ((c >= 'a' && c <= 'z') ||
        (c >= 'A' && c <= 'Z') ||
        (c >= '0' && c <= '9') ||
        c == '-' || c == '_' || c == '.' || c == '~') {
      out += c;
    } else if (c == ' ') {
      out += "%20";
    } else {
      out += '%';
      out += hex[(c >> 4) & 0x0F];
      out += hex[c & 0x0F];
    }
  }
  return out;
}

bool notify_text(const char* text) {
  HTTPClient http;
  String url = String("http://") + BACKEND_HOST + ":" + String(BACKEND_PORT) + "/api/audio/notify?device_id=" + DEVICE_ID + "&text=" + url_encode(text);
  http.begin(url);
  int code = http.GET();
  http.end();
  return code > 0;
}

void wait_for_prompt(unsigned long max_ms) {
  unsigned long start = millis();
  while (prompt_waiting && millis() - start < max_ms) {
    webSocket.loop();
    if (system_state == WS_CONNECTED && millis() - last_heartbeat > HEARTBEAT_INTERVAL) {
      send_heartbeat();
      last_heartbeat = millis();
    }
    delay(10);
  }
  if (prompt_waiting) {
    prompt_waiting = false;
  }
}

void wait_with_ws(unsigned long max_ms) {
  unsigned long start = millis();
  while (millis() - start < max_ms) {
    webSocket.loop();
    if (system_state == WS_CONNECTED && millis() - last_heartbeat > HEARTBEAT_INTERVAL) {
      send_heartbeat();
      last_heartbeat = millis();
    }
    delay(10);
  }
}

// Initialize I2S once (TX + RX)
bool setup_audio() {
  if (audio_initialized) return true;
  
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX | I2S_MODE_RX),
    .sample_rate = AUDIO_SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 256,
    .use_apll = false,
    .tx_desc_auto_clear = true,
    .fixed_mclk = 0
  };
  
  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_BCLK_PIN,
    .ws_io_num = I2S_LRC_PIN,
    .data_out_num = I2S_DOUT_PIN,
    .data_in_num = I2S_DIN_PIN
  };
  
  if (i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL) != ESP_OK) {
    Serial.println("[AUDIO] I2S driver install failed");
    return false;
  }
  
  if (i2s_set_pin(I2S_PORT, &pin_config) != ESP_OK) {
    Serial.println("[AUDIO] I2S pin config failed");
    return false;
  }
  
  audio_initialized = true;
  return true;
}

// Deprecated: setup_i2s_rx/tx are no longer needed as we use single install
bool setup_i2s_rx() { return true; }
bool setup_i2s_tx() { return true; }

void calibrate_wake_threshold() {
  if (!audio_initialized) return;
  uint32_t total = 0;
  int frames = 20;
  int16_t samples[WAKE_FRAME_SAMPLES];
  for (int f = 0; f < frames; f++) {
    size_t bytes_read = 0;
    esp_err_t err = i2s_read(I2S_PORT, samples, sizeof(samples), &bytes_read, portMAX_DELAY);
    if (err != ESP_OK || bytes_read == 0) continue;
    int count = bytes_read / 2;
    uint32_t energy = 0;
    for (int i = 0; i < count; i++) {
      energy += (uint32_t)abs(samples[i]);
    }
    if (count > 0) {
      total += energy / count;
    }
  }
  uint32_t avg = frames > 0 ? total / frames : 0;
  uint32_t desired = avg + WAKE_MARGIN;
  if (desired < (uint32_t)WAKE_THRESHOLD_MIN) desired = WAKE_THRESHOLD_MIN;
  wake_threshold = (int)desired;
}

bool detect_wake_word() {
  if (audio_playing) return false;
  static int wake_hits = 0;
  int16_t samples[WAKE_FRAME_SAMPLES];
  size_t bytes_read = 0;
  esp_err_t err = i2s_read(I2S_PORT, samples, sizeof(samples), &bytes_read, 20 / portTICK_PERIOD_MS);
  if (err != ESP_OK || bytes_read == 0) return false;
  int count = bytes_read / 2;
  uint32_t energy = 0;
  for (int i = 0; i < count; i++) {
    energy += (uint32_t)abs(samples[i]);
  }
  uint32_t avg = energy / count;
  last_wake_level = avg;
  if (avg > (uint32_t)wake_threshold) {
    wake_hits++;
  } else if (wake_hits > 0) {
    wake_hits--;
  }
  if (wake_hits >= WAKE_REQUIRED_FRAMES) {
    wake_hits = 0;
    return true;
  }
  return false;
}

void play_pcm(uint8_t* data, size_t len) {
  if (!data || len == 0) return;
  
  // Switch to TX mode using clock config
  i2s_set_clk(I2S_PORT, AUDIO_SAMPLE_RATE, I2S_BITS_PER_SAMPLE_16BIT, I2S_CHANNEL_MONO);
  audio_playing = true;
  audio_playing_start = millis();
  Serial.printf("[AUDIO] Playback start: %u bytes\n", (unsigned int)len);
  
  size_t bytes_written;
  i2s_write(I2S_PORT, data, len, &bytes_written, portMAX_DELAY);
  
  // Replace zero_dma_buffer with silence flush
  size_t bytes_written_silence;
  uint8_t silence[2048] = {0};
  for (int i = 0; i < 3; i++) {
    i2s_write(I2S_PORT, silence, sizeof(silence), &bytes_written_silence, portMAX_DELAY);
  }
  
  // Reset BCLK/LRCLK for MAX98357 stability
  i2s_stop(I2S_PORT);
  delay(30);
  i2s_start(I2S_PORT);
  
  audio_playing = false;
  last_playback_end = millis();
  
  // Clear DMA for recording
  i2s_zero_dma_buffer(I2S_PORT);
  Serial.println("[AUDIO] Playback end");
}

void play_pcm_chunk(uint8_t* data, size_t len, bool is_last) {
  if (!data || len == 0) return;
  
  if (!audio_playing) {
    // Switch to TX mode using clock config
    i2s_set_clk(I2S_PORT, AUDIO_SAMPLE_RATE, I2S_BITS_PER_SAMPLE_16BIT, I2S_CHANNEL_MONO);
    audio_playing = true;
    audio_playing_start = millis();
    Serial.println("[AUDIO] Stream start");
  }
  
  size_t offset = 0;
  while (offset < len) {
    size_t to_write = len - offset;
    if (to_write > 1024) to_write = 1024;
    size_t bytes_written = 0;
    i2s_write(I2S_PORT, data + offset, to_write, &bytes_written, portMAX_DELAY);
    if (bytes_written == 0) break;
    offset += bytes_written;
    webSocket.loop();
  }
  
  if (is_last) {
    // Replace zero_dma_buffer with silence flush
    size_t bytes_written_silence;
    uint8_t silence[2048] = {0};
    for (int i = 0; i < 3; i++) {
      i2s_write(I2S_PORT, silence, sizeof(silence), &bytes_written_silence, portMAX_DELAY);
    }
    
    // Reset BCLK/LRCLK for MAX98357 stability
    i2s_stop(I2S_PORT);
    delay(30);
    i2s_start(I2S_PORT);
    
    audio_playing = false;
    last_playback_end = millis();
    
    // Clear DMA for recording
    i2s_zero_dma_buffer(I2S_PORT);
    Serial.println("[AUDIO] Stream end");
  }
}

bool record_audio(uint8_t* buffer, size_t total_bytes) {
  size_t offset = 0;
  size_t bytes_read = 0;
  while (offset < total_bytes) {
    size_t to_read = total_bytes - offset;
    if (to_read > 1024) to_read = 1024;
    esp_err_t err = i2s_read(I2S_PORT, buffer + offset, to_read, &bytes_read, portMAX_DELAY);
    if (err != ESP_OK) return false;
    offset += bytes_read;
    webSocket.loop();
    if (system_state == WS_CONNECTED && millis() - last_heartbeat > HEARTBEAT_INTERVAL) {
      send_heartbeat();
      last_heartbeat = millis();
    }
  }
  return true;
}

bool upload_audio(uint8_t* pcm, size_t len, bool is_manual) {
  if (!pcm || len == 0) return false;
  HTTPClient http;
  String url = String("http://") + BACKEND_HOST + ":" + String(BACKEND_PORT) + "/api/audio/upload?device_id=" + DEVICE_ID;
  if (is_manual) {
    url += "&manual=true";
  }
  url += "&level=" + String(last_wake_level);
  url += "&threshold=" + String(wake_threshold);
  http.begin(url);
  http.addHeader("Content-Type", "application/octet-stream");
  int code = http.POST(pcm, len);
  http.end();
  return code > 0;
}

void setup_wifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  system_state = WIFI_CONNECTING;
  Serial.println("[WIFI] Connecting...");
}

void setup_websocket() {
  if (system_state == WS_CONNECTED || system_state == WS_CONNECTING) {
    return;
  }
  if (millis() - last_ws_attempt < WS_RECONNECT_INTERVAL) {
    return;
  }
  webSocket.begin(BACKEND_HOST, BACKEND_PORT, "/ws/camcontroller");
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);
  webSocket.enableHeartbeat(15000, 3000, 2);
  system_state = WS_CONNECTING;
  last_ws_attempt = millis();
  Serial.println("[WS] Connecting to backend...");
}

void send_registration() {
  StaticJsonDocument<256> reg;
  reg["message_type"] = "registration";
  reg["device_type"] = DEVICE_TYPE;
  JsonObject meta = reg.createNestedObject("metadata");
  meta["device_id"] = DEVICE_ID;
  meta["firmware_version"] = FIRMWARE_VERSION;
  meta["capabilities"] = "audio";
  meta["sample_rate"] = AUDIO_SAMPLE_RATE;
  meta["channels"] = AUDIO_CHANNELS;
  meta["bits_per_sample"] = AUDIO_BITS_PER_SAMPLE;
  String out;
  serializeJson(reg, out);
  webSocket.sendTXT(out);
}

void send_heartbeat() {
  StaticJsonDocument<64> hb;
  hb["message_type"] = "heartbeat";
  hb["device_type"] = DEVICE_TYPE;
  String out;
  serializeJson(hb, out);
  webSocket.sendTXT(out);
}

void handle_ws_message(char* payload, size_t len) {
  StaticJsonDocument<1024> doc;
  DeserializationError err = deserializeJson(doc, payload, len);
  if (err) {
    Serial.printf("[WS] JSON parse failed: %s\n", err.c_str());
    return;
  }

  const char* message_type = doc["message_type"];
  if (!message_type) return;

  if (strcmp(message_type, "audio_response") == 0) {
    const char* b64 = doc["audio_base64"];
    if (!b64) return;
    uint8_t* decoded = nullptr;
    size_t decoded_len = decode_base64(b64, &decoded);
    if (decoded && decoded_len > 0) {
      play_pcm(decoded, decoded_len);
    }
    if (decoded) free(decoded);
    if (prompt_waiting) {
      prompt_waiting = false;
    }
  } else if (strcmp(message_type, "audio_chunk") == 0) {
    const char* b64 = doc["audio_base64"];
    if (!b64) return;
    bool is_last = doc["is_last"] | false;
    uint8_t* decoded = nullptr;
    size_t decoded_len = decode_base64(b64, &decoded);
    if (decoded && decoded_len > 0) {
      play_pcm_chunk(decoded, decoded_len, is_last);
    }
    if (decoded) free(decoded);
    if (prompt_waiting && is_last) {
      prompt_waiting = false;
    }
  } else if (strcmp(message_type, "command") == 0) {
    const char* cmd = doc["command_name"];
    if (cmd && strcmp(cmd, "start_recording") == 0) {
      manual_record_requested = true;
      Serial.println("[WS] Manual recording requested");
    }
  }
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      system_state = WS_CONNECTED;
      audio_playing = false; // Reset state on new connection
      last_ws_attempt = millis();
      send_registration();
      Serial.println("[WS] Connected and registered");
      break;
    case WStype_TEXT:
      handle_ws_message((char*)payload, length);
      break;
    case WStype_DISCONNECTED:
      system_state = WIFI_CONNECTED;
      audio_playing = false; // Reset state on disconnect
      last_ws_attempt = millis();
      Serial.printf("[WS] Disconnected (len=%u)\n", (unsigned int)length);
      break;
    case WStype_ERROR:
      Serial.printf("[WS] Error occurred (len=%u)\n", (unsigned int)length);
      break;
    default:
      break;
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  setup_audio();
  calibrate_wake_threshold();
  setup_wifi();
}

void loop() {
  if (WiFi.status() == WL_CONNECTED && system_state == WIFI_CONNECTING) {
    Serial.printf("[WIFI] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
    system_state = WIFI_CONNECTED;
    setup_websocket();
  }

  webSocket.loop();
  
  if (audio_playing) {
    if (millis() - audio_playing_start > AUDIO_PLAYING_TIMEOUT) {
      Serial.println("[AUDIO] Playback timeout! Resetting state.");
      audio_playing = false;
      i2s_zero_dma_buffer(I2S_PORT);
    } else {
      delay(5);
      return;
    }
  }

  if (WiFi.status() == WL_CONNECTED && system_state == WIFI_CONNECTED) {
    if (millis() - last_ws_attempt > WS_RECONNECT_INTERVAL) {
      setup_websocket();
    }
  }

  if (system_state == WS_CONNECTED && millis() - last_heartbeat > HEARTBEAT_INTERVAL) {
    send_heartbeat();
    last_heartbeat = millis();
  }

  if (system_state == WS_CONNECTED && audio_initialized && !audio_playing) {
    unsigned long now = millis();
    bool should_record = false;

    if (manual_record_requested) {
      should_record = true;
      manual_record_requested = false;
    } else if (now - last_wake_time > (unsigned long)WAKE_COOLDOWN_MS && now - last_playback_end > 800) {
      if (detect_wake_word()) {
        last_wake_time = now;
        prompt_waiting = true;
        notify_text("Yes sir I am listening");
        wait_for_prompt(4000);
        wait_with_ws(1000);
        should_record = true;
      }
    }

    if (should_record) {
      last_wake_time = now;
      size_t total_bytes = (size_t)AUDIO_SAMPLE_RATE * RECORD_SECONDS * (AUDIO_BITS_PER_SAMPLE / 8) * AUDIO_CHANNELS;
      
      Serial.printf("[AUDIO] Allocating %u bytes (Heap: %u, PSRAM: %u)\n", total_bytes, esp_get_free_heap_size(), heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
      uint8_t* pcm = (uint8_t*)heap_caps_malloc(total_bytes, MALLOC_CAP_SPIRAM);
      
      // Fallback: Adaptive sizing for internal RAM
      if (!pcm) {
         Serial.println("[AUDIO] PSRAM failed. Trying internal RAM with adaptive size...");
         // Try 5 seconds (160KB) which fits in ~240KB heap
         size_t reduced_seconds = 5;
         total_bytes = (size_t)AUDIO_SAMPLE_RATE * reduced_seconds * (AUDIO_BITS_PER_SAMPLE / 8) * AUDIO_CHANNELS;
         pcm = (uint8_t*)malloc(total_bytes);
         
         if (!pcm) {
             // Try 3 seconds (96KB) as last resort
             reduced_seconds = 3;
             total_bytes = (size_t)AUDIO_SAMPLE_RATE * reduced_seconds * (AUDIO_BITS_PER_SAMPLE / 8) * AUDIO_CHANNELS;
             pcm = (uint8_t*)malloc(total_bytes);
         }
         
         if (pcm) {
             Serial.printf("[AUDIO] Success: allocated %u seconds (%u bytes) in internal RAM\n", reduced_seconds, total_bytes);
         }
      }
      
      if (pcm) {
        if (record_audio(pcm, total_bytes)) {
          prompt_waiting = true;
          notify_text("Sending voice to backend");
          wait_for_prompt(2000);
          if (system_state == WS_CONNECTED && millis() - last_heartbeat > HEARTBEAT_INTERVAL) {
            send_heartbeat();
            last_heartbeat = millis();
          }
          upload_audio(pcm, total_bytes, true);
        }
        free(pcm);
      } else {
        Serial.println("[ERROR] Malloc failed! Not enough memory.");
        notify_text("Memory error");
      }
    }
  }
}

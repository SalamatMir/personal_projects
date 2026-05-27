#include <driver/i2s.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <math.h>

// ────────────────────────────────────────
// OLED
// ────────────────────────────────────────
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
#define OLED_ADDRESS  0x3C
#define OLED_SDA      21
#define OLED_SCL      22

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// ────────────────────────────────────────
// BUTTONS
// Pin 12 → cycle mode
// Pin 14 → reset BPM (heart mode only)
// ────────────────────────────────────────
#define BTN_MODE   14
#define BTN_RESET  12
#define DEBOUNCE_MS 50

typedef enum { BTN_EVT_MODE = 1, BTN_EVT_RESET = 2 } BtnEvent;
QueueHandle_t buttonQueue;

// ────────────────────────────────────────
// MODES
// ────────────────────────────────────────
enum Mode { MODE_WELCOME = 0, MODE_HEART = 1, MODE_LUNG = 2 };
volatile Mode currentMode = MODE_WELCOME;
const int TOTAL_MODES = 3;

// ────────────────────────────────────────
// ICONS
// ────────────────────────────────────────
#define HEART_ICON_WIDTH  32
#define HEART_ICON_HEIGHT 32
const unsigned char PROGMEM heart_icon[] = {
  0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
  0x03,0xf8,0x1f,0xc0,0x07,0xfc,0x3f,0xe0,0x0f,0xfe,0x7f,0xf0,
  0x1f,0xff,0xff,0xf8,0x3f,0xff,0xff,0xfc,0x3f,0xff,0xff,0xfc,
  0x3f,0xff,0xff,0xfc,0x3f,0xff,0xff,0xfc,0x3f,0xff,0xff,0xfc,
  0x3f,0xff,0xff,0xfc,0x3f,0xff,0xff,0xfc,0x1f,0xff,0xff,0xf8,
  0x1f,0xff,0xff,0xf8,0x0f,0xff,0xff,0xf0,0x0f,0xff,0xff,0xe0,
  0x07,0xff,0xff,0xc0,0x03,0xff,0xff,0x80,0x01,0xff,0xff,0x00,
  0x00,0xff,0xfe,0x00,0x00,0x3f,0xfc,0x00,0x00,0x1f,0xf8,0x00,
  0x00,0x0f,0xf0,0x00,0x00,0x07,0xe0,0x00,0x00,0x03,0xc0,0x00,
  0x00,0x01,0x80,0x00,0x00,0x01,0x80,0x00,0x00,0x00,0x00,0x00,
  0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00
};

#define LUNG_ICON_WIDTH  32
#define LUNG_ICON_HEIGHT 32
const unsigned char PROGMEM lung_icon[] = {
  // Inverted lungs bitmap (32x33)
0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
0x00, 0x01, 0x80, 0x00, 0x00, 0x01, 0x84, 0x00,
0x00, 0x71, 0x8F, 0x00, 0x01, 0xF9, 0x9F, 0x80,
0x01, 0xF9, 0x9F, 0xC0, 0x03, 0xF9, 0x9F, 0xE0,
0x07, 0xF9, 0x9F, 0xE0, 0x0F, 0xF9, 0x9F, 0xF0,
0x0F, 0xFF, 0xFF, 0xF0, 0x1F, 0xFF, 0xFF, 0xF8,
0x1F, 0xFF, 0xFF, 0xF8, 0x1F, 0xFE, 0x7F, 0xFC,
0x3F, 0xFC, 0x3F, 0xFC, 0x3F, 0xFC, 0x3F, 0xFC,
0x3F, 0xFC, 0x3F, 0xFC, 0x3F, 0xFC, 0x3F, 0xFC,
0x3F, 0xFC, 0x3F, 0xFC, 0x7F, 0xFC, 0x3F, 0xFE,
0x7F, 0xFC, 0x3F, 0xFE, 0x7F, 0xFC, 0x3F, 0xFE,
0x7F, 0xFC, 0x3F, 0xFE, 0x7F, 0xF8, 0x1F, 0xFE,
0x7F, 0xF8, 0x1F, 0xFE, 0x7F, 0xF8, 0x1F, 0xFE,
0x7F, 0xF0, 0x0F, 0xFE, 0x7F, 0xE0, 0x07, 0xFE,
0x7F, 0x00, 0x00, 0x7E, 0x3C, 0x00, 0x00, 0x1C,
0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
};


// ────────────────────────────────────────
// AUDIO
// ────────────────────────────────────────
#define I2S_WS       33
#define I2S_SCK      32
#define I2S_SD       35
#define I2S_PORT     I2S_NUM_0
#define SAMPLE_RATE  8000
#define SAMPLES      512

#define INMP441_SHIFT  8
#define INMP441_SCALE  8388608.0f
#define DISPLAY_GAIN   40.0f

// ── Display buffer (envelope, downsampled) ──
// Exactly your original style: store envelope at display rate
#define DISPLAY_FS      50
#define DISPLAY_SECONDS 5
#define DISPLAY_SAMPLES (DISPLAY_FS * DISPLAY_SECONDS)   // 250
const int downsampleFactor = SAMPLE_RATE / DISPLAY_FS;   // 160

float displayBuffer[DISPLAY_SAMPLES];
int   displayIndex      = 0;
int   downsampleCounter = 0;

// ────────────────────────────────────────
// ORIGINAL BIQUAD FILTERS
// ────────────────────────────────────────
typedef struct { float x1, x2, y1, y2; } BiquadState;

BiquadState hp_state = {0,0,0,0};
BiquadState lp_state = {0,0,0,0};

const float* active_hp_b;
const float* active_hp_a;
const float* active_lp_b;
const float* active_lp_a;

// Heart: 30–300 Hz
const float heart_hp_b[3] = { 0.9659f, -1.9318f,  0.9659f };
const float heart_hp_a[3] = { 1.0000f, -1.9315f,  0.9359f };
const float heart_lp_b[3] = { 0.0367f,  0.0734f,  0.0367f };
const float heart_lp_a[3] = { 1.0000f, -1.5704f,  0.6913f };

// Lung: 150–1000 Hz
const float lung_hp_b[3]  = { 0.7776f, -1.5552f,  0.7776f };
const float lung_hp_a[3]  = { 1.0000f, -1.5529f,  0.8359f };
const float lung_lp_b[3]  = { 0.2929f,  0.5858f,  0.2929f };
const float lung_lp_a[3]  = { 1.0000f, -0.5858f,  0.1716f };

// ────────────────────────────────────────
// ENVELOPE STATE
// ────────────────────────────────────────
float envAvg      = 0.0f;
float prevEnv     = 0.0f;
float prevPrevEnv = 0.0f;

// ────────────────────────────────────────
// QUEUES
// ────────────────────────────────────────
QueueHandle_t audioQueue;
typedef struct { int32_t samples[SAMPLES]; } AudioBlock;
int32_t i2sRaw[SAMPLES];

// ────────────────────────────────────────
// I2S CONFIG (INMP441)
// ────────────────────────────────────────
static const i2s_config_t i2s_config = {
    .mode                 = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate          = SAMPLE_RATE,
    .bits_per_sample      = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format       = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_I2S_MSB,
    .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count        = 8,
    .dma_buf_len          = 64,
    .use_apll             = true,
    .tx_desc_auto_clear   = false,
    .fixed_mclk           = 0
};
static const i2s_pin_config_t pin_config = {
    .bck_io_num   = I2S_SCK,
    .ws_io_num    = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num  = I2S_SD
};

// ────────────────────────────────────────
// BIQUAD (original Direct Form I)
// ────────────────────────────────────────
float applyBiquad(float x, BiquadState* s,
                  const float b[3], const float a[3]) {
    float y = b[0]*x + b[1]*s->x1 + b[2]*s->x2
                     - a[1]*s->y1  - a[2]*s->y2;
    s->x2 = s->x1; s->x1 = x;
    s->y2 = s->y1; s->y1 = y;
    return y;
}

// ────────────────────────────────────────
// RESET HELPERS
// ────────────────────────────────────────
void resetFilters() {
    hp_state = {0,0,0,0};
    lp_state = {0,0,0,0};
    envAvg = prevEnv = prevPrevEnv = 0.0f;
}

void resetDisplayBuffer() {
    memset(displayBuffer, 0, sizeof(displayBuffer));
    displayIndex      = 0;
    downsampleCounter = 0;
}

void applyModeFilters(Mode m) {
    if (m == MODE_LUNG) {
        active_hp_b = lung_hp_b;  active_hp_a = lung_hp_a;
        active_lp_b = lung_lp_b;  active_lp_a = lung_lp_a;
    } else {
        active_hp_b = heart_hp_b; active_hp_a = heart_hp_a;
        active_lp_b = heart_lp_b; active_lp_a = heart_lp_a;
    }
    resetFilters();
    resetDisplayBuffer();
}

// ────────────────────────────────────────
// TASK 1: I2S — Core 0, priority 5
// ────────────────────────────────────────
void i2s_sampling_task(void *arg) {
    size_t bytesRead;
    AudioBlock block;
    for (;;) {
        if (i2s_read(I2S_PORT, i2sRaw,
                     SAMPLES * sizeof(int32_t),
                     &bytesRead, portMAX_DELAY) == ESP_OK
            && bytesRead == SAMPLES * sizeof(int32_t)) {
            memcpy(block.samples, i2sRaw, bytesRead);
            xQueueSend(audioQueue, &block, 0);
        }
    }
}

// ────────────────────────────────────────
// TASK 2: BUTTON — Core 1, priority 10
// ────────────────────────────────────────
void button_task(void *arg) {
    struct Btn {
        uint8_t  pin;
        uint8_t  evt;
        bool     lastRaw;
        bool     stable;
        uint32_t changedAt;
    };
    Btn btns[2] = {
        { BTN_MODE,  BTN_EVT_MODE,  false, false, 0 },
        { BTN_RESET, BTN_EVT_RESET, false, false, 0 }
    };
    for (int i = 0; i < 2; i++)
        btns[i].lastRaw = (digitalRead(btns[i].pin) == LOW);

    for (;;) {
        uint32_t now = (uint32_t)millis();
        for (int i = 0; i < 2; i++) {
            bool pressed = (digitalRead(btns[i].pin) == LOW);
            if (pressed != btns[i].lastRaw) {
                btns[i].lastRaw   = pressed;
                btns[i].changedAt = now;
            }
            if ((now - btns[i].changedAt) >= DEBOUNCE_MS) {
                if (pressed && !btns[i].stable) {
                    btns[i].stable = true;
                    xQueueSend(buttonQueue, &btns[i].evt, 0);
                    Serial.printf("[BTN] pin%d evt%d\n",
                                  btns[i].pin, btns[i].evt);
                } else if (!pressed && btns[i].stable) {
                    btns[i].stable = false;
                }
            }
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

// ────────────────────────────────────────
// TASK 3: DSP + DISPLAY — Core 1, priority 3
// Display style matches your original exactly:
//   Heart:   icon(top-left) + BPM(top-right) + envelope waveform(bottom)
//   Lung:    icon(top-left) + label + envelope waveform(bottom)
//   Welcome: centred icon + prompt text
// ────────────────────────────────────────
void dsp_and_display_task(void *arg) {
    AudioBlock block;

    float env = 0.0f;
    const float alpha = 0.995f;          // original smoothing

    unsigned long lastBeatTime  = 0;
    int           beatCounter   = 0;
    int           currentBPM    = 0;
    unsigned long lastBPMUpdate = 0;
    const unsigned long MIN_BEAT_INTERVAL_MS = 800;  // original

    // Flash overlay state
    const char*   flashMsg   = nullptr;
    unsigned long flashUntil = 0;

    unsigned long lastDebugTime  = 0;
    float         debugMaxRaw    = 0;
    float         debugMaxFilt   = 0;

    for (;;) {

        // ── Button events ──────────────────────────────
        uint8_t evt;
        while (xQueueReceive(buttonQueue, &evt, 0) == pdPASS) {
            if (evt == BTN_EVT_MODE) {
                currentMode = (Mode)(((int)currentMode + 1) % TOTAL_MODES);
                applyModeFilters(currentMode);
                env         = 0.0f;
                beatCounter = currentBPM = 0;
                lastBPMUpdate = lastBeatTime = 0;
                flashMsg   = currentMode == MODE_WELCOME ? "Welcome"    :
                             currentMode == MODE_HEART   ? "Heart Mode" :
                                                           "Lung Mode";
                flashUntil = millis() + 700;
                Serial.printf("[MODE] %s\n", flashMsg);

            } else if (evt == BTN_EVT_RESET) {
                if (currentMode == MODE_HEART) {
                    env           = 0.0f;
                    beatCounter   = 0;
                    currentBPM    = 0;
                    lastBeatTime  = 0;
                    lastBPMUpdate = millis();
                    envAvg = prevEnv = prevPrevEnv = 0.0f;
                    flashMsg   = "BPM Reset!";
                    flashUntil = millis() + 700;
                    Serial.println("[BPM] Reset.");
                } else {
                    flashMsg   = "Heart mode only";
                    flashUntil = millis() + 700;
                }
            }
        }

        // ── Flash overlay ──────────────────────────────
        if (flashMsg && millis() < flashUntil) {
            display.clearDisplay();
            display.setTextSize(2);
            display.setTextColor(SSD1306_WHITE);
            int16_t x1, y1; uint16_t w, h;
            display.getTextBounds(flashMsg, 0, 0, &x1, &y1, &w, &h);
            display.setCursor((SCREEN_WIDTH  - w) / 2,
                              (SCREEN_HEIGHT - h) / 2);
            display.print(flashMsg);
            display.display();
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        } else {
            flashMsg = nullptr;
        }

        // ── Welcome screen ─────────────────────────────
        if (currentMode == MODE_WELCOME) {
            display.clearDisplay();
            display.setTextSize(1);
            display.setTextColor(SSD1306_WHITE);
            display.setCursor(4, 0);
            display.print("DIGITAL STETHOSCOPE");
            display.drawBitmap(25, 17, heart_icon,
                               HEART_ICON_WIDTH, HEART_ICON_HEIGHT,
                               SSD1306_WHITE);
            display.drawBitmap(70, 17, lung_icon,
                               LUNG_ICON_WIDTH, LUNG_ICON_HEIGHT,
                               SSD1306_WHITE);

            display.setCursor(0, 55);
            display.print("Press button to start");
            display.display();
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }

        // ── Audio DSP ──────────────────────────────────
        if (xQueueReceive(audioQueue, &block, pdMS_TO_TICKS(100)) == pdPASS) {

            // 1. Convert INMP441 → float & DC removal
            float fsamples[SAMPLES];
            float mean = 0.0f;
            for (int i = 0; i < SAMPLES; i++) {
                int32_t s24  = block.samples[i] >> INMP441_SHIFT;
                fsamples[i]  = (float)s24 / INMP441_SCALE;
                mean        += fsamples[i];
                if (fabsf(fsamples[i]) > debugMaxRaw)
                    debugMaxRaw = fabsf(fsamples[i]);
            }
            mean /= SAMPLES;
            for (int i = 0; i < SAMPLES; i++) fsamples[i] -= mean;

            // 2. Bandpass (original single-stage biquads)
            float filtered[SAMPLES];
            for (int i = 0; i < SAMPLES; i++) {
                float s     = applyBiquad(fsamples[i], &hp_state,
                                          active_hp_b, active_hp_a);
                filtered[i] = applyBiquad(s, &lp_state,
                                          active_lp_b, active_lp_a);
                filtered[i] *= DISPLAY_GAIN;
                if (fabsf(filtered[i]) > debugMaxFilt)
                    debugMaxFilt = fabsf(filtered[i]);
            }

            // 3. Envelope + downsample → displayBuffer
            //    Exactly your original algorithm
            for (int i = 0; i < SAMPLES; i++) {
                float rectified = fabsf(filtered[i]);
                env = alpha * env + (1.0f - alpha) * rectified;

                downsampleCounter++;
                if (downsampleCounter >= downsampleFactor) {
                    downsampleCounter = 0;
                    displayBuffer[displayIndex] = env;

                    // Beat detection (heart mode only)
                    if (currentMode == MODE_HEART) {
                        unsigned long now = millis();
                        envAvg = 0.999f * envAvg + 0.001f * env;
                        float threshold = envAvg * 1.5f;

                        if (prevEnv    > threshold   &&
                            prevEnv    > prevPrevEnv  &&
                            prevEnv    > env          &&
                            (now - lastBeatTime) > MIN_BEAT_INTERVAL_MS) {
                            lastBeatTime = now;
                            beatCounter++;
                        }
                        prevPrevEnv = prevEnv;
                        prevEnv     = env;
                    }

                    displayIndex = (displayIndex + 1) % DISPLAY_SAMPLES;
                }
            }

            // 4. BPM update every 10 s
            unsigned long now = millis();
            if (currentMode == MODE_HEART && (now - lastBPMUpdate) > 10000UL) {
                if (lastBPMUpdate > 0) {
                    currentBPM = (int)((beatCounter * 60000UL)
                                       / (now - lastBPMUpdate));
                    currentBPM = constrain(currentBPM, 0, 150);
                }
                beatCounter   = 0;
                lastBPMUpdate = now;
            }

            // 5. Debug every 2 s
            if (now - lastDebugTime > 2000UL) {
                Serial.printf("[DBG] Raw=%.5f Filt=%.5f BPM=%d\n",
                              debugMaxRaw, debugMaxFilt, currentBPM);
                debugMaxRaw = debugMaxFilt = 0.0f;
                lastDebugTime = now;
            }

            // ─────────── DRAW OLED ───────────
            // Exactly your original layout, enlarged waveform area
            display.clearDisplay();
            display.setTextSize(1);
            display.setTextColor(SSD1306_WHITE);
            display.setCursor(4, 0);

            if (currentMode == MODE_HEART) {
                // ── Top area: icon left, BPM right ──
                display.print("Heart Sound");

                // Heart icon — small 32×32 in top-left
                display.drawBitmap(0, 8, heart_icon,
                                   HEART_ICON_WIDTH, HEART_ICON_HEIGHT,
                                   SSD1306_WHITE);

                // BPM — large text, right side
                display.setTextSize(1);
                display.setCursor(55, 18);
                display.print("BPM: ");
                display.setTextSize(2);
                display.setCursor(87, 12);
                display.print(currentBPM);
                display.setTextSize(1);
    

            } else {
                // ── Lung top area: icon left, label right ──
                display.print("Lung Sound");

                display.drawBitmap(0, 8, lung_icon,
                                   LUNG_ICON_WIDTH, LUNG_ICON_HEIGHT,
                                   SSD1306_WHITE);

                display.setTextSize(1);
                display.setCursor(52, 15);
                display.print("Breath");
                display.setCursor(52, 26);
                display.print("Monitor");
            }

            // ── Waveform — bottom half (y: 42 to 63) ──
            // Exactly your original drawing algorithm,
            // just using the full bottom 22 pixels
            {
                // Separator
            

                const int WY_TOP  = 32;
                const int WY_BOT  = 63;
                const int WY_SPAN = WY_BOT - WY_TOP;   // 21 px

                // Find min/max of envelope buffer (your original method)
                float minV = displayBuffer[0];
                float maxV = displayBuffer[0];
                for (int i = 1; i < DISPLAY_SAMPLES; i++) {
                    if (displayBuffer[i] < minV) minV = displayBuffer[i];
                    if (displayBuffer[i] > maxV) maxV = displayBuffer[i];
                }
                float range = maxV - minV;
                if (range < 1e-4f) range = 1e-4f;

                // Draw waveform (your original loop, adapted to new y range)
                int prevY = WY_BOT;
                for (int x = 0; x < SCREEN_WIDTH; x++) {
                    int pos = (displayIndex +
                               x * DISPLAY_SAMPLES / SCREEN_WIDTH)
                              % DISPLAY_SAMPLES;

                    // Map envelope value → pixel row
                    // Higher envelope = taller peak = lower y number
                    int y = WY_BOT - (int)((displayBuffer[pos] - minV)
                                           / range * WY_SPAN);
                    y = constrain(y, WY_TOP, WY_BOT);

                    if (x > 0) display.drawLine(x-1, prevY, x, y, SSD1306_WHITE);
                    prevY = y;
                }
            }

            display.display();
        }

        vTaskDelay(1);
    }
}

// ────────────────────────────────────────
// SETUP
// ────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(500);

    pinMode(BTN_MODE,  INPUT_PULLUP);
    pinMode(BTN_RESET, INPUT_PULLUP);

    Serial.printf("Pin %d (MODE)  = %s\n", BTN_MODE,
        digitalRead(BTN_MODE)  == HIGH ? "HIGH ok" : "LOW! check wiring");
    Serial.printf("Pin %d (RESET) = %s\n", BTN_RESET,
        digitalRead(BTN_RESET) == HIGH ? "HIGH ok" : "LOW! check wiring");

    Wire.begin(OLED_SDA, OLED_SCL);
    if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS)) {
        Serial.println("OLED failed!"); for(;;);
    }
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println("Starting...");
    display.setTextSize(2);
    display.setCursor(0, 13);
    display.println("WELLCOME");
    display.setTextSize(1);

    display.setCursor(0, 40);
    display.println("Developed By:");

    String name = "Engr. Salamat Ali";

    display.setCursor(0, 50);

    // Animate name letter by letter
    for (int i = 0; i < name.length(); i++) {
        display.print(name[i]);
        display.display();
        delay(150);
    }

    delay(1000);
    

    applyModeFilters(MODE_WELCOME);

    i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
    i2s_set_pin(I2S_PORT, &pin_config);
    i2s_start(I2S_PORT);

    audioQueue  = xQueueCreate(4,  sizeof(AudioBlock));
    buttonQueue = xQueueCreate(10, sizeof(uint8_t));

    // Core 0: I2S only          (priority 5)
    // Core 1: Button            (priority 10)
    // Core 1: DSP + Display     (priority 3)
    xTaskCreatePinnedToCore(i2s_sampling_task,    "I2S",  4096,  NULL, 5,  NULL, 0);
    xTaskCreatePinnedToCore(button_task,          "BTN",  2048,  NULL, 10, NULL, 1);
    xTaskCreatePinnedToCore(dsp_and_display_task, "DSP",  16384, NULL, 3,  NULL, 1);

    Serial.println("Ready.  Pin12=Mode  Pin14=Reset BPM");
}

// ────────────────────────────────────────
// LOOP — empty
// ────────────────────────────────────────
void loop() {
    vTaskDelay(pdMS_TO_TICKS(1000));
}
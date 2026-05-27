#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Keypad.h>
#include "MAX30105.h"
#include "spo2_algorithm.h"
#include "disease_model.h"  // your DecisionTree model

/* ================= OLED ================= */
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

/* ================= KEYPAD ================= */
#define ROWS 4
#define COLS 3
char keys[ROWS][COLS] = {
  {'*','0','#'},
  {'1','2','3'},
  {'4','5','6'},
  {'7','8','9'}
};
byte rowPins[ROWS] = {16,17,18,19};
byte colPins[COLS] = {23,26,25};
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

/* ================= MAX30105 ================= */
MAX30105 particleSensor;
#define HR_BUFFER 50
uint32_t irBuffer[HR_BUFFER];
uint32_t redBuffer[HR_BUFFER];

/* ================= DATA ================= */
// Glucose
float glucoseRaw = 0;
float glucoseSmoothed = 50;
const int GLUCOSE_SAMPLES = 30;
float glucoseHistory[GLUCOSE_SAMPLES];
int glucoseIndex = 0;
float glucoseAlpha = 0.2; // EMA smoothing

// Heart Rate & SpO2
const int HR_SAMPLES = 10;
int hrHistory[HR_SAMPLES] = {70};
int spo2History[HR_SAMPLES] = {95};
int hrIndex = 0;
int spo2Index = 0;
int heartRateSmoothed = 70;
int spo2Smoothed = 95;

/* ================= ML ================= */
float ml_features[10] = {0};
int predictedDisease = -1;

const char* disease_names[] = {
  "Hypoglycemia", "Normal", "Hyperglycemia", "Tachycardia", "Bradycardia"
};
const char* input_labels[] = {
  "Age",
  "Weight (kg)",
  "BMI"
};

/* ================= STATE ================= */
enum DeviceState {
  WELCOME_SCREEN,
  PLACE_FINGER,
  MENU,
  HR_SCREEN,
  GLUCOSE_SCREEN,
  BOTH_SCREEN,
  ML_INPUT,
  ML_RESULT
};
volatile DeviceState state = WELCOME_SCREEN;

/* ================= USER INPUT ================= */
String userInput = "";
int inputIndex = 0;

/* ================= RTOS ================= */
QueueHandle_t keypadQueue;

/* ================= SENSOR TASKS ================= */
void HeartRateTask(void *pv) {
  while(true){
    if(particleSensor.getIR() > 50000){
      // Fill HR/Red buffer
      for(int i=0;i<HR_BUFFER;i++){
        while(!particleSensor.available()) particleSensor.check();
        irBuffer[i] = particleSensor.getIR();
        redBuffer[i] = particleSensor.getRed();
        particleSensor.nextSample();
      }

      int32_t hr, spo2Val;
      int8_t vhr, vs;

      // Call void function directly
      maxim_heart_rate_and_oxygen_saturation(
        irBuffer, HR_BUFFER, redBuffer,
        &spo2Val, &vs, &hr, &vhr
      );

      // Only accept valid HR/SPO2
      if(hr > 0 && spo2Val > 0){
        hrHistory[hrIndex++] = hr;
        if(hrIndex >= HR_SAMPLES) hrIndex = 0;
        spo2History[spo2Index++] = spo2Val;
        if(spo2Index >= HR_SAMPLES) spo2Index = 0;

        // Compute moving average
        int hrSum=0, spo2Sum=0;
        for(int i=0;i<HR_SAMPLES;i++){
          hrSum += hrHistory[i];
          spo2Sum += spo2History[i];
        }
        heartRateSmoothed = hrSum / HR_SAMPLES;
        spo2Smoothed = spo2Sum / HR_SAMPLES;
      }
    }
    vTaskDelay(pdMS_TO_TICKS(500));
  }
}

void GlucoseTask(void *pv) {
  while(true){
    // Map ADC to realistic glucose range 70-150 mg/dL
    glucoseRaw = map(analogRead(35), 0, 4095, 70, 150);

    // Update circular buffer
    glucoseHistory[glucoseIndex++] = glucoseRaw;
    if(glucoseIndex >= GLUCOSE_SAMPLES) glucoseIndex = 0;

    // Moving average
    float sum = 0;
    for(int i=0;i<GLUCOSE_SAMPLES;i++) sum += glucoseHistory[i];
    float avg = sum / GLUCOSE_SAMPLES;

    // EMA smoothing
    glucoseSmoothed = glucoseAlpha * avg + (1 - glucoseAlpha) * glucoseSmoothed;

    vTaskDelay(pdMS_TO_TICKS(500));
  }
}

/* ================= KEYPAD TASK ================= */
void KeypadTask(void *pv) {
  char key;
  while(true){
    key = keypad.getKey();
    if(key) xQueueSend(keypadQueue, &key, 0);
    vTaskDelay(pdMS_TO_TICKS(30));
  }
}

/* ================= DISPLAY TASK ================= */
void DisplayTask(void *pv){
  while(true){
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);

    switch(state){
      case WELCOME_SCREEN:
        display.setTextSize(1);
        display.setCursor(0,0);
        display.setCursor(0,0);
        display.println("Non-Invasive");
        display.println("HR & Glucose");
        display.println("Monitoring");
        display.println("Sabtain & Ishaq");
        display.println("-------------------");
        display.println("Press any key...");
        break;

      case PLACE_FINGER:
        display.setTextSize(2);
        display.setCursor(0,10);
        display.println("Place Finger");
        display.setTextSize(1);
        display.setCursor(0,55);
        display.println("to measure HR & GLU");
        break;

      case MENU:
        display.setTextSize(2);
        display.setCursor(0,0);
        display.println("1: HR");
        display.println("2: GLU");
        display.println("3: BOTH");
        display.setTextSize(1);
        display.setCursor(15,50);
        display.println("Enter option:");
        break;

      case HR_SCREEN:
        display.setTextSize(2);
        display.setCursor(0,0);
        display.print("HR: "); display.print(heartRateSmoothed);
        display.setTextSize(1);
        display.setCursor(0,55);
        display.print("*Predict       #Back");
        break;

      case GLUCOSE_SCREEN:
        display.setTextSize(2);
        display.setCursor(0,0);
        display.print("GLU: "); display.print((int)glucoseSmoothed);
        display.setTextSize(1);
        display.setCursor(0,55);
        display.print("*Predict  #Back");
        break;

      case BOTH_SCREEN:
        display.setTextSize(2);
        display.setCursor(0,0);
        display.print("HR: "); display.print(heartRateSmoothed);
        display.setCursor(0,20);
        display.print("GLU: "); display.print((int)glucoseSmoothed);
        display.setTextSize(1);
        display.setCursor(0,55);
        display.print("*Predict  #Back");
        break;

      case ML_INPUT:
        display.setTextSize(1);
        display.setCursor(0,0);
        display.print("Enter "); display.print(input_labels[inputIndex]);
        display.setTextSize(2);
        display.setCursor(0,18);
        display.print(userInput);
        display.setTextSize(1);
        display.setCursor(0,55);
        display.print("*Next  #Del");
        break;

      case ML_RESULT:
        display.setTextSize(1);
        display.setCursor(0,0);
        display.println("Prediction:");
        display.setTextSize(2);
        display.setCursor(0,18);
        display.println(disease_names[predictedDisease]);
        display.setTextSize(1);
        display.setCursor(0,55);
        display.println("Press any key...");
        break;
    }

    display.display();
    vTaskDelay(pdMS_TO_TICKS(200));
  }
}

/* ================= STATE TASK ================= */
void StateTask(void *pv) {
  char key;

  while (true) {
    if (xQueueReceive(keypadQueue, &key, portMAX_DELAY)) {

      switch (state) {

        case WELCOME_SCREEN:
          state = PLACE_FINGER;
          break;

        case PLACE_FINGER:
          state = MENU;
          break;

        case MENU:
          if (key == '1') state = HR_SCREEN;
          else if (key == '2') state = GLUCOSE_SCREEN;
          else if (key == '3') state = BOTH_SCREEN;
          break;

        case HR_SCREEN:
        case GLUCOSE_SCREEN:
        case BOTH_SCREEN:
          if (key == '#') {
            state = MENU;
          }
          else if (key == '*') {
            // Reset ML input
            inputIndex = 0;
            userInput = "";

            // Inject sensor values CORRECTLY
            ml_features[3] = glucoseSmoothed;      // Glucose
            ml_features[4] = heartRateSmoothed;    // Heart Rate

            state = ML_INPUT;
          }
          break;

        case ML_INPUT:
          if (isDigit(key)) {
            userInput += key;
          }
          else if (key == '#' && userInput.length() > 0) {
            userInput.remove(userInput.length() - 1);
          }
          else if (key == '*') {
            ml_features[inputIndex] = userInput.toFloat();
            inputIndex++;
            userInput = "";

            // Only 3 manual inputs: Age, Weight, BMI
            if (inputIndex >= 3) {
              predictedDisease = model.predict(ml_features);
              state = ML_RESULT;
            }
          }
          break;

        case ML_RESULT:
          state = MENU;
          break;
      }
    }
  }
}


/* ================= SETUP ================= */
void setup(){
  Serial.begin(115200);
  Wire.begin();

  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.clearDisplay();
  display.display();

  particleSensor.begin(Wire);
  particleSensor.setup();

  keypadQueue = xQueueCreate(10, sizeof(char));

  for(int i=0;i<GLUCOSE_SAMPLES;i++) glucoseHistory[i]=100;
  for(int i=0;i<HR_SAMPLES;i++) hrHistory[i]=70, spo2History[i]=95;

  xTaskCreatePinnedToCore(HeartRateTask, "HeartRate", 4096, NULL, 2, NULL, 1);
  xTaskCreatePinnedToCore(GlucoseTask, "Glucose", 2048, NULL, 2, NULL, 1);
  xTaskCreatePinnedToCore(KeypadTask, "Keypad", 2048, NULL, 3, NULL, 1);
  xTaskCreatePinnedToCore(DisplayTask, "Display", 4096, NULL, 1, NULL, 0);
  xTaskCreatePinnedToCore(StateTask, "State", 4096, NULL, 3, NULL, 0);
}

void loop(){}

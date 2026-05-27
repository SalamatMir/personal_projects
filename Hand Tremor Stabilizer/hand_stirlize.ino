#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// OLED settings (128x64 I2C, default address 0x3C)
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// ────────────────────────────────────────────────
// Pins
#define BTN_TOGGLE_MOTORS  12
#define BTN_TOGGLE_LED     13
#define LED1               32
#define LED2               33   // lights when motors are running

// Motor driver pins (both channels for two vibrators)
#define ENA  19
#define IN1  18
#define IN2   5
#define ENB   4
#define IN3  17
#define IN4  16

// PWM settings (ESP32 core 3.x+ style)
#define PWM_FREQ  5000
#define PWM_RES      8   // 0-255
#define MOTOR_SPEED 180  // 0-255, adjust if too strong/weak

bool motorsOn = false;
bool led1On   = false;

// ────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println("Button + Motor + LED + OLED Test");

  Wire.begin();  // SDA=21, SCL=22 default

  // Init OLED
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED failed → check wiring/address");
    while (1);
  }
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 20);
  display.println("Test Starting...");
  display.display();
  delay(1200);

  // Motor pins
  pinMode(ENA, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(ENB, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  // Motors forward direction
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);

  // Attach PWM (new API)
  ledcAttach(ENA, PWM_FREQ, PWM_RES);
  ledcAttach(ENB, PWM_FREQ, PWM_RES);

  stopMotors();

  // Buttons & LEDs
  pinMode(BTN_TOGGLE_MOTORS, INPUT_PULLUP);
  pinMode(BTN_TOGGLE_LED,    INPUT_PULLUP);
  pinMode(LED1, OUTPUT);
  pinMode(LED2, OUTPUT);
  digitalWrite(LED1, LOW);
  digitalWrite(LED2, LOW);

  updateOLED();
}

// ────────────────────────────────────────────────
void loop() {
  // Read buttons (active LOW)
  static unsigned long lastDebounce = 0;
  const unsigned long debounceDelay = 250;

  if (millis() - lastDebounce > debounceDelay) {
    if (!digitalRead(BTN_TOGGLE_MOTORS)) {
      motorsOn = !motorsOn;
      lastDebounce = millis();
      if (motorsOn) {
        setBothMotors(MOTOR_SPEED);
        digitalWrite(LED2, HIGH);
      } else {
        stopMotors();
        digitalWrite(LED2, LOW);
      }
      updateOLED();
      Serial.println(motorsOn ? "Motors ON" : "Motors OFF");
    }

    if (!digitalRead(BTN_TOGGLE_LED)) {
      led1On = !led1On;
      lastDebounce = millis();
      digitalWrite(LED1, led1On ? HIGH : LOW);
      updateOLED();
      Serial.println(led1On ? "LED1 ON" : "LED1 OFF");
    }
  }

  delay(30);  // small loop delay
}

// ────────────────────────────────────────────────
void setBothMotors(int pwm) {
  ledcWrite(ENA, pwm);
  ledcWrite(ENB, pwm);
}

void stopMotors() {
  ledcWrite(ENA, 0);
  ledcWrite(ENB, 0);
}

void updateOLED() {
  display.clearDisplay();
  display.setCursor(0, 0);
  display.setTextSize(1);

  display.println("BUTTON TEST MODE");
  display.println("---------------");

  display.print("Motors: ");
  display.println(motorsOn ? "ON" : "OFF");

  display.print("LED1:   ");
  display.println(led1On ? "ON" : "OFF");

  display.print("LED2:   ");
  display.println(motorsOn ? "ON (vib)" : "OFF");

  display.setCursor(0, 48);
  display.print("BTN12: Motors  BTN13: LED");

  display.display();
}
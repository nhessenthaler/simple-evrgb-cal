#include <Adafruit_GFX.h>
#include <MCUFRIEND_kbv.h>
#include <UTFTGLUE.h>
#include <TouchScreen.h>
#include "charuco_bitmap.h"

MCUFRIEND_kbv tft;
UTFTGLUE myGLCD(0, A2, A1, A3, A4, A0);

// --- Einstellungen ---
const float TARGET_FPS = 15; // Gewünschte FPS
unsigned long lastUpdate = 0;
bool invertedStatus = false;

const int BMP_WIDTH = 400; 
const int BMP_HEIGHT = 320;

void setup() {
    uint16_t ID = tft.readID();
    tft.begin(ID);
    tft.setRotation(1);
    
    // Einmalig das Bild zeichnen (Schwarz auf Weiß)
    tft.fillScreen(0xFFFF); 
    int x = (tft.width() - BMP_WIDTH) / 2;
    int y = (tft.height() - BMP_HEIGHT) / 2;
    tft.drawBitmap(x, y, charuco_bitmap, BMP_WIDTH, BMP_HEIGHT, 0xFFFF, 0x0000);
}

void loop() {
    unsigned long interval = 1000.0 / TARGET_FPS;
    unsigned long currentMillis = millis();

    if (currentMillis - lastUpdate >= interval) {
        lastUpdate = currentMillis;

        // Den Display-Controller anweisen, die Farben zu invertieren
        invertedStatus = !invertedStatus;
        tft.invertDisplay(invertedStatus);
    }
}
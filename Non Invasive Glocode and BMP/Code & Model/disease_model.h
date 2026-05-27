#pragma once

namespace Eloquent {
namespace ML {
namespace Port {

class DecisionTree {
public:
    /**
     * Feature vector:
     * x[0] = Age
     * x[1] = Weight (kg)
     * x[2] = Height (cm)
     * x[3] = Glucose (mg/dL)
     * x[4] = Heart Rate (BPM)
     *
     * Output classes:
     * 0 = Hypoglycemia
     * 1 = Normal
     * 2 = Hyperglycemia
     * 3 = Tachycardia
     * 4 = Bradycardia
     */
    int predict(float *x) {

        float glucose = x[3];
        float heartRate = x[4];

        // --- Glucose-based decisions ---
        if (glucose < 70.0) {
            return 0; // Hypoglycemia
        }

        if (glucose > 140.0) {
            return 2; // Hyperglycemia
        }

        // --- Heart-rate-based decisions (only if glucose is normal) ---
        if (heartRate > 100.0) {
            return 3; // Tachycardia
        }

        if (heartRate < 60.0) {
            return 4; // Bradycardia
        }

        // --- Normal condition ---
        return 1; // Normal
    }
};

} // namespace Port
} // namespace ML
} // namespace Eloquent

// Global model instance
Eloquent::ML::Port::DecisionTree model;

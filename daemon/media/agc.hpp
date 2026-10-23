#pragma once

#include <QtGlobal>
#include <cmath>

// Automatic gain control for the AirPods uplink. The raw stream decodes quiet, so a call
// sounds faint without it. Free of audio types so it is testable on its own.
namespace OpenPods::HiRes
{
    class Agc
    {
    public:
        // Walks the frame in place, tracking the envelope and easing the gain towards the
        // level that puts speech near the target.
        void process(qint16 *samples, int count)
        {
            for (int i = 0; i < count; ++i) {
                const float x = static_cast<float>(samples[i]) / 32768.0f;
                const float level = std::fabs(x);
                // Rising level is followed quickly so a syllable is not clipped; falling level
                // is followed slowly so a pause does not pump the gain up to the noise floor.
                m_envelope += (level - m_envelope) * (level > m_envelope ? kAttack : kRelease);
                // Below the gate the frame is room tone, and lifting it is what turns a pause
                // into audible fans. Measured on the device: the ceiling gain reached silence
                // within milliseconds and speech and silence arrived at the same level.
                const float desired = m_envelope < kGate
                                          ? 1.0f
                                          : std::min(kTarget / std::max(m_envelope, 1e-4f), kMaxGain);
                m_gain += (desired - m_gain) * kGainEase;
                // tanh keeps a transient inside the range instead of wrapping it.
                samples[i] = static_cast<qint16>(std::tanh(x * m_gain) * 32767.0f);
            }
        }

        float gain() const { return m_gain; }

    private:
        static constexpr float kTarget = 0.25f;   // about -12 dBFS
        static constexpr float kMaxGain = 4.0f;   // about +12 dB
        static constexpr float kGate = 0.01f;     // about -40 dBFS, under which nothing is lifted
        static constexpr float kAttack = 0.02f;
        // Slow enough to hold through the gaps between syllables, so a sentence keeps one gain.
        static constexpr float kRelease = 0.0002f;
        static constexpr float kGainEase = 0.002f;

        float m_envelope = 0.0f;
        float m_gain = 1.0f;
    };
}

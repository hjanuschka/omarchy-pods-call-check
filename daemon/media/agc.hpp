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
                const float desired = std::min(kTarget / std::max(m_envelope, 1e-4f), kMaxGain);
                m_gain += (desired - m_gain) * kGainEase;
                // tanh keeps a transient inside the range instead of wrapping it.
                samples[i] = static_cast<qint16>(std::tanh(x * m_gain) * 32767.0f);
            }
        }

        float gain() const { return m_gain; }

    private:
        static constexpr float kTarget = 0.25f;   // about -12 dBFS
        static constexpr float kMaxGain = 8.0f;   // about +18 dB
        static constexpr float kAttack = 0.02f;
        static constexpr float kRelease = 0.001f;
        static constexpr float kGainEase = 0.01f;

        float m_envelope = 0.0f;
        float m_gain = 1.0f;
    };
}

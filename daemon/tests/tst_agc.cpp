#include <QtTest>

#include "../media/agc.hpp"
#include "../media/eldpcm.hpp"

using namespace OpenPods::HiRes;

// A frame of the uplink's shape: 480 mono samples of a steady tone at a given amplitude.
static QList<qint16> tone(double amplitude, int count = kEldFrameSamples)
{
    QList<qint16> out;
    out.reserve(count);
    for (int i = 0; i < count; ++i) {
        out.append(static_cast<qint16>(std::sin(i * 0.05) * amplitude * 32767.0));
    }
    return out;
}

static double rms(const QList<qint16> &samples)
{
    double sum = 0.0;
    for (qint16 s : samples) {
        sum += double(s) * double(s);
    }
    return std::sqrt(sum / samples.size());
}

class TestAgc : public QObject
{
    Q_OBJECT

private slots:
    void liftsSpeechTowardsTheTarget();
    void leavesTheNoiseFloorAlone();
    void doesNotLiftAnAlreadyLoudFrame();
    void neverExceedsItsGainCeiling();
    void keepsLoudInputInRange();
};

void TestAgc::liftsSpeechTowardsTheTarget()
{
    // The measured uplink sits far below the target, which is the whole reason this exists.
    QList<qint16> speech = tone(0.05);
    const double before = rms(speech);
    Agc agc;
    for (int frame = 0; frame < 40; ++frame) {
        speech = tone(0.05);
        agc.process(speech.data(), speech.size());
    }
    QVERIFY2(rms(speech) > before * 2.0, "speech should end up louder");
    QVERIFY(agc.gain() > 1.0f);
}

void TestAgc::leavesTheNoiseFloorAlone()
{
    // Measured on the device: silence came back at the same level as speech, because the gain
    // rode up to its ceiling whenever nobody was talking and lifted the fans with it.
    QList<qint16> room = tone(0.004);
    const double before = rms(room);
    Agc agc;
    for (int frame = 0; frame < 200; ++frame) {
        room = tone(0.004);
        agc.process(room.data(), room.size());
    }
    QVERIFY2(rms(room) < before * 1.5,
             qPrintable(QStringLiteral("room tone was lifted from %1 to %2").arg(before).arg(rms(room))));
}

void TestAgc::doesNotLiftAnAlreadyLoudFrame()
{
    Agc agc;
    QList<qint16> loud;
    for (int frame = 0; frame < 40; ++frame) {
        loud = tone(0.5);
        agc.process(loud.data(), loud.size());
    }
    QVERIFY2(agc.gain() < 2.0f, "a loud frame needs little gain");
}

void TestAgc::neverExceedsItsGainCeiling()
{
    // Silence drives the desired gain towards its clamp, which must hold.
    Agc agc;
    for (int frame = 0; frame < 2000; ++frame) {
        QList<qint16> silence(kEldFrameSamples, 0);
        agc.process(silence.data(), silence.size());
    }
    QVERIFY(agc.gain() <= 8.0f);
}

void TestAgc::keepsLoudInputInRange()
{
    // Without the limiter a gained transient wraps sign, which is audible as a click.
    Agc agc;
    QList<qint16> full = tone(0.99);
    agc.process(full.data(), full.size());
    for (qint16 s : full) {
        QVERIFY(s >= -32767 && s <= 32767);
    }
}

QTEST_GUILESS_MAIN(TestAgc)
#include "tst_agc.moc"

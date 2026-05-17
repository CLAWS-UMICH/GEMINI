using NUnit.Framework;
using CLAWS.Audio;

public class PcmConverterTests
{
    [Test]
    public void FloatsToInt16_Zero_ProducesZeroBytes()
    {
        var floats = new float[] { 0.0f };
        var bytes = PcmConverter.FloatsToInt16(floats);
        Assert.That(bytes.Length, Is.EqualTo(2));
        Assert.That(bytes[0], Is.EqualTo(0));
        Assert.That(bytes[1], Is.EqualTo(0));
    }

    [Test]
    public void FloatsToInt16_MaxPositive_ProducesShortMax()
    {
        var floats = new float[] { 1.0f };
        var bytes = PcmConverter.FloatsToInt16(floats);
        // short.MaxValue = 32767 = 0x7FFF, little-endian → 0xFF 0x7F
        Assert.That(bytes[0], Is.EqualTo(0xFF));
        Assert.That(bytes[1], Is.EqualTo(0x7F));
    }

    [Test]
    public void FloatsToInt16_MaxNegative_ProducesShortMin()
    {
        var floats = new float[] { -1.0f };
        var bytes = PcmConverter.FloatsToInt16(floats);
        // short.MinValue = -32768 = 0x8000, little-endian → 0x00 0x80
        Assert.That(bytes[0], Is.EqualTo(0x00));
        Assert.That(bytes[1], Is.EqualTo(0x80));
    }

    [Test]
    public void FloatsToInt16_AboveOne_ClampsToShortMax()
    {
        var floats = new float[] { 1.5f, 2.0f };
        var bytes = PcmConverter.FloatsToInt16(floats);
        Assert.That(bytes[0], Is.EqualTo(0xFF));
        Assert.That(bytes[1], Is.EqualTo(0x7F));
        Assert.That(bytes[2], Is.EqualTo(0xFF));
        Assert.That(bytes[3], Is.EqualTo(0x7F));
    }

    [Test]
    public void FloatsToInt16_BelowNegativeOne_ClampsToShortMin()
    {
        var floats = new float[] { -1.5f };
        var bytes = PcmConverter.FloatsToInt16(floats);
        Assert.That(bytes[0], Is.EqualTo(0x00));
        Assert.That(bytes[1], Is.EqualTo(0x80));
    }

    [Test]
    public void FloatsToInt16_EmptyInput_ProducesEmptyOutput()
    {
        var bytes = PcmConverter.FloatsToInt16(new float[0]);
        Assert.That(bytes.Length, Is.EqualTo(0));
    }

    [Test]
    public void FloatsToInt16_KnownMidValue_RoundsToExpectedInt16()
    {
        var bytes = PcmConverter.FloatsToInt16(new float[] { 0.5f });
        short value = (short)(bytes[0] | (bytes[1] << 8));
        Assert.That(value, Is.InRange((short)16380, (short)16386));
    }

    [Test]
    public void ChunkSamples_ExactMultiple_ProducesEqualChunks()
    {
        var samples = new float[3200]; // 2 chunks of 1600
        var chunks = PcmConverter.ChunkSamples(samples, chunkSize: 1600);
        Assert.That(chunks.Count, Is.EqualTo(2));
        Assert.That(chunks[0].Length, Is.EqualTo(1600));
        Assert.That(chunks[1].Length, Is.EqualTo(1600));
    }

    [Test]
    public void ChunkSamples_PartialTail_DropsTail()
    {
        // 1700 samples → 1 full chunk of 1600; remainder 100 dropped
        // (Tail handling is the caller's responsibility — keep this function strict.)
        var samples = new float[1700];
        var chunks = PcmConverter.ChunkSamples(samples, chunkSize: 1600);
        Assert.That(chunks.Count, Is.EqualTo(1));
        Assert.That(chunks[0].Length, Is.EqualTo(1600));
    }

    [Test]
    public void ChunkSamples_SmallerThanChunk_ReturnsEmpty()
    {
        var samples = new float[800];
        var chunks = PcmConverter.ChunkSamples(samples, chunkSize: 1600);
        Assert.That(chunks.Count, Is.EqualTo(0));
    }

    [Test]
    public void ChunkSamples_PreservesData()
    {
        var samples = new float[1600];
        for (int i = 0; i < samples.Length; i++) samples[i] = i / 1600f;
        var chunks = PcmConverter.ChunkSamples(samples, chunkSize: 1600);
        Assert.That(chunks.Count, Is.EqualTo(1));
        Assert.That(chunks[0][0], Is.EqualTo(0f));
        Assert.That(chunks[0][1599], Is.EqualTo(1599f / 1600f));
    }
}

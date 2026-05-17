using System;

namespace CLAWS.Audio
{
    public static class PcmConverter
    {
        /// <summary>
        /// Convert float samples in [-1.0, 1.0] to little-endian int16 PCM bytes.
        /// Values outside [-1.0, 1.0] are clamped. Output length is 2 * samples.Length.
        /// Scaling factor is 32768 with intermediate int clamp so -1.0 maps to short.MinValue.
        /// </summary>
        public static byte[] FloatsToInt16(float[] samples)
        {
            if (samples == null || samples.Length == 0)
                return Array.Empty<byte>();

            var bytes = new byte[samples.Length * 2];
            for (int i = 0; i < samples.Length; i++)
            {
                float clamped = samples[i];
                if (clamped > 1.0f) clamped = 1.0f;
                else if (clamped < -1.0f) clamped = -1.0f;

                int scaled = (int)(clamped * 32768f);
                if (scaled > short.MaxValue) scaled = short.MaxValue;
                else if (scaled < short.MinValue) scaled = short.MinValue;

                short value = (short)scaled;
                bytes[i * 2] = (byte)(value & 0xFF);
                bytes[i * 2 + 1] = (byte)((value >> 8) & 0xFF);
            }
            return bytes;
        }
    }
}

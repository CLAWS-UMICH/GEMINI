using NUnit.Framework;

public class SmokeTest
{
    [Test]
    public void SmokeTest_TestRunnerExecutes_Passes()
    {
        Assert.That(1 + 1, Is.EqualTo(2));
    }
}

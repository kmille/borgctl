from borgctl.wordlist import get_passphrase


class TestPassphraseGenerator:

    def test_get_passphrase(self):
        passphrase = get_passphrase()
        assert type(passphrase) is str
        assert passphrase.count("-") == 9
        assert passphrase == passphrase.lower()

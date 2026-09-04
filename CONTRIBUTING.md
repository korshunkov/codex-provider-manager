# Contributing

Thanks for considering a contribution.

1. Open an issue before large behavioral changes.
2. Keep user-facing text clear and concise.
3. Run tests before submitting:

```bash
python3 -m unittest discover -s tests -v
swiftc -parse-as-library -O -o /tmp/ProviderModelPicker src/ProviderModelPicker.swift
```

4. Keep changes focused and describe the user-visible behavior in your pull request.

## Security

Do not open public issues with API keys, credentials, or private server data.
Report security issues as described in `SECURITY.md`.

# 🌰 Acornix community apps

Apps and games made with [Acornix](https://github.com/gonzaroman/acornix), the free AI app builder for Android, and shared by their creators. Open **Explore** in Acornix to browse them, try them without installing, install them with one tap or remix them with your own AI.

Every app here is a single web page made with AI on a phone, often from just one sentence. Each one shows the request that created it, so you can learn how to ask for your own.

## 📱 How to use these apps

- **In Acornix (2.4.0 or newer):** Home › Explore.
- **Without Acornix:** open any `apps/<name>/index.html` in a browser. Apps that use the phone bridge (`window.Acornix`) or your AI only do those things inside Acornix.

## 🗂️ How this repository works

```
apps/<id>/index.html      the app
apps/<id>/app.json        name, emoji, category, description, the request that created it, author
apps/<id>/screenshot.jpg  what you see in the gallery
catalog.json              generated from all of the above; Acornix reads this file
```

`scripts/build_catalog.py` validates every app and writes `catalog.json`. It also labels what each app uses, so people know before installing:

| Label | Meaning |
|---|---|
| `ai` | Uses the AI of whoever runs it (Acornix asks them first) |
| `phone` | Uses phone features through Acornix: speech, flashlight, notifications… |
| `camera` / `microphone` | Asks for the camera or the microphone |
| `internet` | Loads code or data from the internet |

## ✍️ Publishing your app

Publishing from Acornix is coming soon: you will sign in with your GitHub account and tap **Publish to the community**. Every app is reviewed before it appears here: first automatically (including an AI review of its code), then by a person.

### Rules

Apps that break these rules are not accepted, and are removed if reported later.

1. **No personal data.** Don't publish your own data or anyone else's. Acornix only publishes the app's code, never its database or files.
2. **Nothing sent away without a clear reason.** An app may load libraries from a well-known CDN or call a public API it obviously needs. It must not send what the user types, their files or their data anywhere else.
3. **No passwords or payments.** Apps must not ask for passwords, card numbers or other credentials.
4. **No hidden or obfuscated code**, no cryptocurrency mining, and no abusing the user's AI (for example, sending it requests the user didn't ask for).
5. **No adult, violent, hateful or illegal content**, and nothing that targets a real person.
6. **Only what you can share.** Use your own images and sounds, or ones whose license allows it. Don't copy other people's games or brands.

## 📄 License

Everything published here is under the [MIT License](LICENSE): anyone can use, change and remix the apps, keeping the author's name. By publishing an app you agree to share it under this license.

## 🚩 Reporting an app

If an app breaks the rules or doesn't work, [open an issue](https://github.com/gonzaroman/acornix-apps/issues/new) with its name and what's wrong.

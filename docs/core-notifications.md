# Core Notifications API v1

Core Notifications is part of UltraBar Studio 0.52.31 and is installed on Core
when you Deploy. It appears as a built-in entry under **Background apps**.
Select it and choose **Send test notification** to try the banner on Core.
Studio 0.52.32 adds the Bambu print-complete and print-error sounds to that
test panel. **Silent** previews the banner by itself. Core uses its notification
volume and respects silent, vibrate and Do Not Disturb modes for test sounds.
Studio 0.52.33 adds a **Test volume** slider. Core temporarily applies the
nearest device volume step for the test, then restores the previous level.
A setting of 0% plays no sound.

An Android app or an app-backed widget can post directly from its Core process.
Built-in widgets running inside the LineOS launcher use the same API. The
provider starts on demand and runs on Core, including when Studio is closed.

## Android clients

Declare the permission in the calling app manifest. Apps targeting Android 11+
should also declare the provider for package visibility.

```xml
<uses-permission android:name="dk.ultrabarx.notifications.POST"/>
<queries>
    <provider android:authorities="dk.ultrabarx.notifications"/>
</queries>
```

On a worker thread, call the Android content provider:

```java
Uri endpoint = Uri.parse("content://dk.ultrabarx.notifications");
Bundle payload = new Bundle();
payload.putString("title", "Print complete");
payload.putString("message", "The print is ready to remove.");
payload.putString("kind", "success");
Bundle response = context.getContentResolver().call(endpoint, "post.v1", null, payload);
```

Handle an unavailable provider (including `IllegalArgumentException` on devices
where it is absent) and a denied call (`SecurityException`). Treat the capability
as optional and keep the rest of your app operational on older Studio releases.

| Field | Accepted input |
| --- | --- |
| `title` | Plain text, 1–80 Unicode code points |
| `message` | Plain text, 1–200 Unicode code points |
| `kind` | `info` (default), `success`, or `warning` |

The returned Bundle contains a string named `status`.

| Status | Meaning |
| --- | --- |
| `accepted` | Core accepted the banner for immediate or queued display |
| `busy` | The queue is full, or the sending app has three banners waiting |
| `screen_off` | Core is asleep |
| `overlay_unavailable` | Deploy must restore Core's banner permission |
| `invalid` | The payload is invalid |
| `permission_denied` | The caller does not have the posting permission |
| `unknown_method` | The provider does not support this method |

Core derives the source label from the Android calling package. Core owns the
banner placement, colors, typography and four-second display duration. The
banner passes through touch and doesn't wake the screen. The posting API is
silent. Calling apps choose when to post, supply the text, and handle their own
audio. As of Studio 0.52.34, Core shows accepted banners in the order received. Up to eight banners can wait, with a limit of three
waiting per sending app. The queue is in memory and is discarded if Core is
asleep when the next banner is due. Apps should post for meaningful events
and avoid retrying in a loop. Declarative layouts alone do not post
notifications. Use the app code that receives the event.

## Build the bundled APK

Set `ULTRABAR_ANDROID_SDK` to the same Android SDK root used for native widgets,
`CORE_NOTIFICATIONS_KEYSTORE` to the maintained PKCS12 release key, and
`CORE_NOTIFICATIONS_KEY_PASSWORD` in the local build environment. Run
`python core-notifications/build.py` with JDK 17+ and Python 3.
Keep the same signing key for updates. Increment the Android version code
when replacing the APK. The Windows installer includes the verified APK in
Studio's assets.

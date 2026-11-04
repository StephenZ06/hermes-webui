# Business Office setup

Open Office, then Integrations. Pick the business first: every connection
belongs to one business.

The redirect address to register is shown in each provider's panel. Open the
WebUI from the same address you register, because Google and Meta match it
exactly. Google requires `https` (or `localhost`).

## Google (Gmail)

1. In Google Cloud, create a project and enable the Gmail API.
2. Configure the OAuth consent screen and add yourself as a test user.
3. Add the scopes `gmail.readonly` and `gmail.compose`.
4. Create an OAuth client of type Web application and add the redirect address.
5. Paste the client ID and secret in the Gmail panel, then choose Sign in.

Both scopes are restricted. While the app is in Testing, Google ends the sign-in
after 7 days and shows a warning screen. Publishing it may require verification.

## Threads

1. Create a Meta app with the Threads use case and the `threads_basic` permission.
2. Add the redirect address to the app's valid OAuth URIs.
3. Paste the Threads app ID and secret, then choose Sign in.

## Instagram

Needs an Instagram professional account.

1. Add Instagram with Business Login to a Meta app, with `instagram_business_basic`.
2. Add the redirect address.
3. Paste the Instagram app ID and secret, then choose Sign in.

## Obsidian

Connect the vault on the Notes page. In the Obsidian panel, grant folders to this
business and tick what each agent may do. Nothing is reachable until you do.

## Key

Set `HERMES_BUSINESS_OFFICE_KEY` (urlsafe base64 of 32 bytes) to keep the
encryption key apart from the state folder. Changing it makes stored secrets
unreadable, so accounts must sign in again.

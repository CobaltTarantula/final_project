# Deployment preparation

The app now has a WSGI entry point (`wsgi:app`), an environment-configurable
SQLite path, and a `/health` endpoint for hosting checks. For a Linux host with
Gunicorn, install `requirements-production.txt` and start it with:

```sh
gunicorn --workers 1 --bind 0.0.0.0:${PORT:-8000} wsgi:app
```

Set these environment variables in the hosting dashboard:

- `APP_ENV=production`
- `SECRET_KEY` to a randomly generated secret
- MongoDB Atlas connection string and database name
- Firebase project configuration and server-side Admin SDK credentials
- Cloudflare Turnstile site key and secret key

## No-cost hosting target

Use a Render Free Web Service for Flask and a MongoDB Atlas Free cluster for
application data. This avoids depending on Render's local filesystem for
accounts, suggestions, lexicon entries, and history. The existing app uses
SQLite, so it still needs a MongoDB/PyMongo data-layer migration before this
hosting combination can run.

Both services have free tiers, but this is a hobby/demo setup with limits, not
reliable production hosting. Render spins down a free web service after 15
minutes without traffic, and the next request can take about a minute to start.
Its filesystem is ephemeral, so SQLite data stored there would be lost. Atlas
Free has a 0.5 GB limit for documents plus indexes, no managed backups, and may
pause after 30 days with no connections. A 600,000-entry lexicon may fit or may
exceed the Atlas storage limit depending on document and index sizes; measure
the imported data before relying on this tier. Export backups regularly with
`mongodump` and keep them outside the cluster.

Atlas requires an IP access list. Render uses regional outbound IP ranges shared
by services in that region; configure the current ranges for the chosen Render
region in Atlas, rather than opening database access to every IP. Use a
dedicated Atlas database user with access limited to this application's
database, and keep its credentials in Render environment variables.

## Next steps

1. **Check free-tier capacity.** Measure a representative lexicon import, including
   normalized lookup fields and indexes, against Atlas Free's 0.5 GB cap. Decide
   whether the 600,000-entry target fits before committing to the free cluster.
   Establish a manual export/restore routine because the free tier has no managed
   backups.
2. **Move persistence from SQLite to MongoDB.** Add PyMongo and replace SQLite
   queries with a small data-access layer. Model languages and translation pairs
   explicitly, then scope lexicon entries and grammar rules to a pair so another
   original language can be added without another hard-coded translator. Create
   collections for languages/pairs, lexicon, rules, history, user roles, and
   suggestions. Add indexes for pair-scoped normalized word lookups, unique
   Firebase UID, each user's history, and pending suggestions. Migrate and compare
   the existing Faeric lexicon, pronunciation, and grammar rules.
3. **Add Firebase Authentication.** Enable email/password sign-up and email
   verification. Visitors can translate without signing in, but anonymous
   translations are not saved. Require a verified account for personal history
   and dictionary suggestions. Keep passwords in Firebase, not MongoDB.
4. **Enforce authorization in Flask.** Verify Firebase identity on the server;
   filter history by the authenticated UID. Store roles in a server-controlled
   profile or Firebase custom claim. New accounts are ordinary users; bootstrap
   the admin role separately so users cannot grant it to themselves.
5. **Add signup and form protections.** Put Cloudflare Turnstile on registration
   and validate each token server-side. Add rate limits for sign-up, verification
   resend, and login. Add CSRF protection to state-changing forms.
6. **Add the dictionary review flow.** Users can submit suggestions, but only an
   admin can approve/reject them or directly change active lexicon entries.
   Record the submitter, review status, and reviewer for each suggestion.
7. **Prepare production configuration.** Configure Atlas IP access and a
   least-privilege database user. Put the MongoDB URI, Firebase Admin credentials,
   Turnstile secret, Flask secret, and public Firebase/Turnstile settings in
   Render environment variables. Update `/health` to check MongoDB rather than
   SQLite, and make sure application startup no longer creates or depends on the
   local SQLite file.
8. **Deploy a test release, then announce it.** Connect the repository to a Render
   Free Web Service using the Gunicorn command above. Verify anonymous
   translation, sign-up/verification, private history, suggestion submission,
   admin review, and recovery/backup procedures before sharing the public URL.

The code still uses SQLite locally; none of the authentication, authorization,
MongoDB persistence, or review-queue steps above are implemented yet. Keep
production secrets in the hosting environment, never in Git.

Firebase Authentication's no-cost Spark tier currently allows 100 new accounts
per hour from each IP address and 1,000 address-verification emails per day.
Cloudflare Turnstile also offers a free plan. These controls reduce automated
sign-ups but cannot guarantee that abuse is impossible, especially from many
different networks. Keep a modest account-creation rate limit in the app too.

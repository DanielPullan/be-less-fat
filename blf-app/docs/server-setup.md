# Installing Be Less Fat on 3264.uk

Be Less Fat goes on the same server as SecureMy.School and Johto (`3264.uk`, Ubuntu 24.04), at
**https://blf.3264.uk**. It's set up the same way: gunicorn runs the app, systemd keeps it running, Apache faces the
internet with a Let's Encrypt certificate, and the data is in PostgreSQL. The other sites aren't touched.

| | SecureMy.School | Johto | Be Less Fat |
|---|---|---|---|
| Address | https://securemy.school | https://johto.3264.uk | https://blf.3264.uk |
| Folder | `/home/dan/SecureMySchool` | `/home/dan/Johto` | `/home/dan/BeLessFat` (the app is in its `blf-app` folder) |
| Service | `securemyschool` (8000; staging 8001) | `johto` (8002) | `belessfat` (8003) |
| Database | `securemyschool` | `johto` | `belessfat` |
| Apache site | `securemy.school.conf` | `johto.3264.uk.conf` | `blf.3264.uk.conf` |
| Backups | `~/securemyschool-backups` | `~/johto-backups` | `~/belessfat-backups` |

> **A different address?** Replace `blf.3264.uk` in this guide and in `deploy/apache-belessfat.conf` before you start.

It takes about 20 minutes. Step 1 and the "bring your data" parts of step 6 run on your Mac; everything else runs
**on the server**.

---

## 1. Point blf.3264.uk at the server

Wherever 3264.uk's DNS is managed (DigitalOcean → Networking → Domains, if it's with the others), add an **A record**:
host `blf`, pointing at the server's IP address, **134.209.182.232**.

Check it from your Mac before going on (it can take a few minutes):

```bash
dig +short blf.3264.uk
```

It should print the IP address. If it prints nothing, wait and try again: the certificate in step 9 needs it.

## 2. Connect to the server

```bash
ssh dan@3264.uk
```

Your prompt should change to `dan@timford`. If it doesn't, you're still on your Mac.

## 3. Get the code

The repository is public, so no key is needed. Be Less Fat is on the **`ai`** branch, in its `blf-app` folder:

```bash
git clone -b ai https://github.com/DanielPullan/be-less-fat.git /home/dan/BeLessFat
cd /home/dan/BeLessFat/blf-app
```

Every command from here on runs in `/home/dan/BeLessFat/blf-app`.

## 4. Install the packages

uv is already on the server for SecureMy.School.

```bash
uv sync
```

## 5. Make the database

```bash
sudo -u postgres createdb -O dan belessfat
psql belessfat -c 'select 1'
```

The second line should print a little table with `1` in it: `dan` can reach the new database without a password,
the same way the other apps do.

## 6. Settings, and your data

First decide: **start fresh**, or **bring the data from your Mac** (your account, goals, weigh-ins and food)?

### Starting fresh

```bash
cat > .env <<EOF
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
DATABASE_URL=postgresql:///belessfat
BEHIND_PROXY=1
EOF
chmod 600 .env
uv run flask --app app db upgrade
```

### Bringing the data from your Mac

On your **Mac**, in the app's folder, bring its database up to date, note its secret key, and send the database
to the server:

```bash
cd ~/path/to/be-less-fat/blf-app        # wherever it is on your Mac
git pull
uv run flask --app app db upgrade
grep SECRET_KEY .env
scp instance/app.db dan@3264.uk:~/blf-from-mac.db
```

Then on the **server**, use **the same secret key** (paste it in place of `PASTE-THE-MAC-KEY-HERE`), so
authenticator app codes keep working:

```bash
cat > .env <<'EOF'
SECRET_KEY=PASTE-THE-MAC-KEY-HERE
DATABASE_URL=postgresql:///belessfat
BEHIND_PROXY=1
EOF
chmod 600 .env
uv run flask --app app db upgrade
uv run flask --app app copy-from-sqlite ~/blf-from-mac.db
rm ~/blf-from-mac.db
```

`copy-from-sqlite` lists each table and how many rows it copied, then "Copied N rows". It only copies into an empty
database, so do it **before** anyone signs up on the new site.

> Coming from the **old** Be Less Fat (before Kanto, `blf_app/blf.sqlite3`)? Copy that file to the server instead
> and run `uv run flask --app app import-old-blf ~/blf.sqlite3 --admin yourname`.

Either way, **keep a copy of `SECRET_KEY` somewhere safe** (your password manager), away from the backups. Without
it, a restored database still works, but everyone's authenticator app has to be set up again.

## 7. Your account

If you brought your data, your account came with it: make it an admin (skip if it already is):

```bash
uv run flask --app app set-role yourname admin
uv run flask --app app set-role yourname global_admin
```

Starting fresh, make it:

```bash
uv run flask --app app create-user yourname --role member --role admin --role global_admin
```

(It asks for your password twice.)

**Anyone can sign up.** Be Less Fat has **Sign up** on its sign-in page, so anyone who finds blf.3264.uk can make an
account (they only see their own food and weight). If it should just be you and people you add, change
`ALLOW_SIGN_UP = True` to `False` in `settings.py` before step 8, and add people from the Users page instead.

## 8. Start it under systemd

```bash
sudo cp deploy/belessfat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now belessfat
systemctl status belessfat --no-pager
```

It should say **active (running)**. Check it answers:

```bash
curl -sI http://127.0.0.1:8003/login | head -1
```

That should print `HTTP/1.1 200 OK`. If not, see [When something's wrong](#when-somethings-wrong).

## 9. Add the Apache site and the certificate

```bash
sudo a2enmod proxy proxy_http headers
sudo cp deploy/apache-belessfat.conf /etc/apache2/sites-available/blf.3264.uk.conf
sudo a2ensite blf.3264.uk
sudo apache2ctl configtest
```

**Only if that says `Syntax OK`**, reload Apache. A reload with a broken config would take every site on the server
down, SecureMy.School included.

```bash
sudo systemctl reload apache2
```

`http://blf.3264.uk` should now show Be Less Fat's front page. Then get the certificate:

```bash
sudo certbot --apache -d blf.3264.uk
```

If it asks whether to redirect http to https, choose **redirect**.

## 10. Turn on secure cookies and passkeys

Now that HTTPS works:

```bash
printf 'SECURE_COOKIES=1\nPASSKEY_RP_ID=blf.3264.uk\nPASSKEY_ORIGIN=https://blf.3264.uk\n' >> .env
sudo systemctl restart belessfat
```

Passkeys belong to one address. **Ones you made on your Mac (at 127.0.0.1 or localhost) don't work at
blf.3264.uk**: sign in with your password (and authenticator code, if you use one), then add a new passkey on your
profile (click your name, then **Security → Add a passkey**) and remove the old one.

## 11. Check the firewall

Nothing new needs opening: the app listens only on the server itself.

```bash
sudo ufw status
```

There should be no rule for port 8003. `OpenSSH` and `Apache Full` should be allowed, as for the other sites.

## 12. Sign in and check

At **https://blf.3264.uk**: sign in, and if you brought your data, check Today, Food and Weight look as they did on
your Mac. Add a passkey (step 10). Check https://securemy.school and https://johto.3264.uk still work too.

## 13. Nightly backups

```bash
crontab -e
```

Add this line under the others (it runs at 2:50am, after SecureMy.School's and Johto's):

```
50 2 * * * /home/dan/BeLessFat/blf-app/deploy/backup.sh belessfat
```

Run it once by hand to check it works:

```bash
/home/dan/BeLessFat/blf-app/deploy/backup.sh belessfat && ls -l ~/belessfat-backups
```

It keeps one dump per weekday, so the last 7 days. **Copy `~/belessfat-backups` off the server regularly**, with the
other apps' backups.

---

## Updating to a new version

```bash
ssh dan@3264.uk
cd /home/dan/BeLessFat/blf-app
/home/dan/BeLessFat/blf-app/deploy/backup.sh belessfat      # a backup first
git pull
uv sync
sudo systemctl restart belessfat
```

Database changes are applied automatically when it starts. Then sign in and open Today to check it.

## Day to day

| To… | Run |
|---|---|
| Restart it | `sudo systemctl restart belessfat` |
| See whether it's running | `systemctl status belessfat --no-pager` |
| Follow the app's log | `journalctl -u belessfat -f` |
| See Apache's log for the site | `sudo tail /var/log/apache2/belessfat-error.log` (and `belessfat-access.log`) |
| Run a command (`create-user`, `set-role`, `reset-mfa`…) | `cd /home/dan/BeLessFat/blf-app`, then `uv run flask --app app <command>` |
| Check certificate renewal works | `sudo certbot renew --dry-run` (covers every site's certificate) |

## Restoring a backup

```bash
sudo systemctl stop belessfat
pg_restore --clean --if-exists -d belessfat ~/belessfat-backups/belessfat-Mon.dump     # the day you want
sudo systemctl start belessfat
```

## When something's wrong

| What you see | What to do |
|---|---|
| **Service Unavailable** or **Proxy Error** in the browser | The app isn't running: `journalctl -u belessfat -n 50 --no-pager` says why |
| `status` says **failed**, and the log mentions `SECRET_KEY` | `.env` is missing or not in `/home/dan/BeLessFat/blf-app` |
| The log says **address already in use** | Something else has port 8003 (`sudo ss -ltnp | grep 8003`). Choose another port in both `deploy/belessfat.service` (then `/etc/systemd/system/`) and the Apache site |
| The log mentions **database "belessfat" does not exist** or a role | Step 5 didn't work: run it again |
| `copy-from-sqlite` says the database **already has data** | Someone signed up, or it was run twice. To start the copy again: `sudo -u postgres dropdb belessfat`, then steps 5 and 6 |
| `copy-from-sqlite` says a table **is missing** columns | Run `uv run flask --app app db upgrade` on the Mac (after `git pull`) and send the file again |
| Authenticator codes are refused after bringing your data | `SECRET_KEY` isn't the Mac's: put the Mac's in `.env` and restart. Or `uv run flask --app app reset-mfa yourname` and set it up again |
| Signing in just comes back to the sign-in page | `SECURE_COOKIES=1` is on but you're on `http://`: use `https://blf.3264.uk` |
| **Passkeys** don't offer to sign in, or fail | Passkeys from the Mac don't carry over (step 10). Otherwise check `PASSKEY_RP_ID` and `PASSKEY_ORIGIN` in `.env`, then restart |
| Apache shows "Index of /" or another site | The site isn't enabled: `ls /etc/apache2/sites-enabled/` should list `blf.3264.uk.conf` |

# Daily run — launchd setup

The pipeline runs daily via a launchd agent. The real `.plist` is **gitignored**
(it contains machine-specific absolute paths); only the template is tracked.

## Required environment (in `~/.zshrc`)

The wrapper sources `export` lines from `~/.zshrc`. Set:

```sh
export NASS_API_KEY="..."          # USDA QuickStats
export MARS_API_KEY="..."          # USDA MyMarketNews (retail)
export GMAIL_APP_PASSWORD="..."    # Gmail app password for the summary email
export PORK_EMAIL_FROM="you@gmail.com"
export PORK_EMAIL_TO="a@example.org,b@example.org"   # comma-separated
```

## Install / update the agent

```sh
cd "$(git rev-parse --show-toplevel)"
# Render the template with this machine's paths:
sed -e "s|__PROJECT_DIR__|$PWD|g" -e "s|__HOME__|$HOME|g" \
    deploy/com.innovateanimalag.porkchartbook.plist.template \
    > deploy/com.innovateanimalag.porkchartbook.plist

# Install + load:
cp deploy/com.innovateanimalag.porkchartbook.plist "$HOME/Library/LaunchAgents/"
launchctl bootout  gui/$(id -u)/com.innovateanimalag.porkchartbook 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.innovateanimalag.porkchartbook.plist"
```

## Run by hand

```sh
bash update_pork_chartbook.sh            # real run (ingest -> build -> push -> email)
bash update_pork_chartbook.sh --dry-run  # no push, no email
```

Logs: `~/pork_chartbook.log` (run detail) and `~/pork_chartbook_launchd.log` (launchd stdout/err).

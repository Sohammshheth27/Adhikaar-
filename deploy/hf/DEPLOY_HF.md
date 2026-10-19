# Deploy Adhikaar to a Hugging Face Docker Space (free)

One container serves the **engine + the web UI** on an HTTPS URL. ~16 GB RAM free tier.

## 1. Create the Space
1. Sign in at huggingface.co → **New Space**.
2. Owner: you · Space name: `adhikaar` · **SDK: Docker** (blank template) · Hardware: **CPU basic (free)**.
3. Create it. You now have a git repo at `https://huggingface.co/spaces/<you>/adhikaar`.

## 2. Put the app in the Space repo
From your Adhikaar checkout (`D:\Adhikaar`), push the code to the Space. The 86 MB model needs **git-lfs**.

```bash
# one-time
git lfs install

# add the Space as a remote (use your Space URL)
git remote add hf https://huggingface.co/spaces/<you>/adhikaar

# HF needs the model tracked by LFS
git lfs track "*.safetensors"
git add .gitattributes

# use the HF front-matter README as the Space's README (required for Docker SDK)
cp deploy/hf/README.md README.hf.md    # keep your GitHub README intact locally

# push the current branch to the Space's main
git push hf main
```

> If the push is rejected because the Space already has a README, either let HF keep its auto-generated
> front-matter README, or copy `deploy/hf/README.md` over `README.md` in the Space and commit. The
> Space README **must** contain the `sdk: docker` + `app_port: 7860` front matter.

Authenticate with a **Hugging Face access token** (Settings → Access Tokens, `write` scope) when git prompts.

## 3. Let it build
HF builds the Dockerfile (installs Playwright + Chromium + the model). First build ~5–10 min. When it
finishes, the Space is live at `https://<you>-adhikaar.hf.space` — open it and the scanner UI loads.

## 4. (Optional) Turn on the LLM judge for top accuracy
Space → **Settings → Variables and secrets** → add secrets:
```
ADHIKAAR_LLM_JUDGE = 1
ADHIKAAR_LLM_PROVIDER = openai
ADHIKAAR_LLM_BASE_URL = https://generativelanguage.googleapis.com/v1beta/openai
ADHIKAAR_LLM_API_KEY = <your Gemini key>
ADHIKAAR_LLM_MODEL = gemini-3.6-flash
```
Restart the Space. Without these it uses the offline fine-tuned model (free, still accurate).

## 5. (Optional) Site on GitHub Pages, engine on HF
If you host the UI separately on GitHub Pages, set the backend URL before the app loads (e.g. in the
page `<head>`):
```html
<script>window.ADHIKAAR_API = "https://<you>-adhikaar.hf.space";</script>
```
CORS is already open on the engine, so the Pages site can call it.

## Notes
- **Sleep:** free Spaces pause after 48 h idle (30–90 s cold start on next visit).
- **Blocking:** crawls run from HF's datacenter IP — hard anti-bot sites may block; normal sites work.
- **Health check:** `https://<you>-adhikaar.hf.space/health` should return `{"status":"ok","checks":47}`.

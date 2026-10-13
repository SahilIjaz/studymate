---
title: StudyMate API
emoji: 📚
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 8000
pinned: false
license: mit
---

# StudyMate API

Backend for [StudyMate](https://github.com/SahilIjaz/studymate): ask questions about your own PDFs and get
answers with page-level citations, streamed from Gemini.

This Space only wraps the image built by the repository's CI (`ghcr.io/sahilijaz/studymate-api:main`).

Settings → Variables and secrets:

| Kind | Name | Value |
|---|---|---|
| Secret | `GEMINI_API_KEY` | your key from aistudio.google.com |
| Variable | `LLM_PROVIDER` | `gemini` |
| Variable | `EMBEDDING_PROVIDER` | `gemini` |
| Variable | `CORS_ORIGINS` | the Vercel URL, e.g. `https://studymate-ai.vercel.app` |

Health: `/health` · Docs: `/docs`

# Production verification

Verified on 2026-10-18 through the owner-private Site API proxy. The test client polled each analysis/download job, then streamed the entire attachment and checked the MP4 container signature. No preview/demo media was used.

| Platform | Extract | Download | Bytes | Public test URL |
|---|---|---|---:|---|
| YouTube | error | not reached | — | https://www.youtube.com/watch?v=jNQXAC9IVRw |
| TikTok | done | done | 2027898 | https://www.tiktok.com/@patroxofficial/video/6742501081818877190 |
| Instagram | done | done | 918120 | https://www.instagram.com/reel/Chunk8-jurw/ |
| Facebook | done | done | 95023 | https://www.facebook.com/100033620354545/videos/106560053808006/ |
| Snapchat | done | done | 583698 | https://www.snapchat.com/spotlight/W7_EDlXWTBiXAEEniNoMPwAAYYWtidGhudGZpAX1TKn0JAX1TKnXJAAAAAA |
| X | done | done | 720270 | https://x.com/TopHeroes_/status/2001950365332455490 |

YouTube remains blocked: the final token-provider + alternate-client attempt returned AUTH_REQUIRED (sign-in / anti-bot verification). Earlier attempts also received HTTP 403 from player API requests. One earlier attempt exposed 240p for the public test video but failed to download; that is not counted as success. The YouTube link read from the user screenshot also failed extraction and is not treated as verified.

The other five platforms each produced a full downloadable MP4 attachment. X was rechecked after adding a refresh-on-expired-stream fallback; that final download returned 720270 bytes. Successful links do not imply every post on a platform is accessible; removed, private, age/region restricted or platform-blocked media can fail.

Backend code deployed: 0edf26de621995b3a0adb1962e6a26eeb190f8f1. TikTok, Instagram, Facebook and Snapchat downloads passed on the immediately preceding engine revision; token-provider additions affect YouTube only. X passed on the final revision.

Mobile document checks: HTTP 200, RTL Arabic, viewport-fit=cover, compact phone-app layout, old landing-page hero removed, standalone web manifest. Browser visual QA is unavailable in this environment. TypeScript, production build and five backend tests passed.

The site is not represented as supporting successful YouTube downloads from the current cloud host. Further work requires an authorized session/verification path or a suitable external download service/proxy that the owner explicitly configures. No account cookies were collected, and no paid resource was created.

## Follow-up after the user reported failures (15:21 UTC)

Actual user requests were IP-blocked: TikTok video 7687664674376060167 and YouTube v2MOPr2SoD0. This overrides any implication that an earlier successful example proves platform-wide support. Both Render and the Site edge also received HTTP 403 from the TikTok resolver.

The phone frontend now resolves public TikTok metadata through the CORS-enabled public TikWM endpoint without credentials. The private engine validates the video ID, HTTPS TikTok-owned CDN host, duration and size, then downloads the media. A production API test submitted the same resolver metadata and streamed the complete 5036909-byte MP4 attachment for the user's actual TikTok post. This verifies the server pipeline; a mobile browser could not be exercised in this environment. TikWM returned Access-Control-Allow-Origin: *.

The 15:15 UTC production rerun downloaded full MP4 attachments for the Instagram, Facebook, Snapchat and X examples above (918120, 95023, 583698 and 720270 bytes respectively). These are sample links, not the user's unspecified failing posts. YouTube v2MOPr2SoD0 remains blocked; no successful YouTube download is claimed.

The save control is now a normal same-origin download anchor activated by the user after preparation, rather than a synthetic click after asynchronous polling. Six backend tests, TypeScript and the production build passed. Engine revision 1505c075210ea4fece45909da16907a1f9d5ce70 is live.

## Batch verification requested by owner (2026-10-18, 15:54 UTC)

Tested 22 distinct public post URLs (25 runs including three X regression retests). Each successful attachment was saved in full, hashed with SHA-256, probed with ffprobe, and fully decoded with ffmpeg including all audio streams.

| Platform | Verified different videos | Different URLs attempted |
|---|---:|---:|
| YouTube | 0 | 3 |
| TikTok | 3 | 3 |
| Instagram | 4 | 5 |
| Facebook | 3 | 5 |
| Snapchat | 3 | 3 |
| X | 3 | 3 |

The first X downloads were structurally playable but silent: normalize discarded HLS audio-only formats when acodec was missing. Engine 10 retains audio based on vcodec=none and merges MP4 audio with MP4 video. All three original X posts were re-downloaded at 720p with AAC audio after deployment, fully decoded without errors: 3406779, 1406439 and 4327311 bytes. This corrects earlier success reports that checked the container without checking audio streams.

The Instagram Chunk8-jurw and aye83DjauH results contain no audio stream; the API advertises their available video choices as audio=false. Other tested Instagram videos contain AAC audio. One Instagram URL and two Facebook URLs failed and remain recorded in the audit; their failures were not erased when additional links passed. All three YouTube links failed cloud anti-bot/access checks.

The private Site HTTP path was tested, with TikTok public-resolution requests emulating the frontend. Actual mobile-browser UI and every format/MP3 conversion were not tested. Seven backend tests passed. Backend code commit: fc78c58304b4935a95dbbf73dd0e428de41daba4.

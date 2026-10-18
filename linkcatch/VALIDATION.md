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

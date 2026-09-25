# What actually makes a short product/launch video work (2025–2026)

Evidence review + a concrete cut plan for the Tower hype film.
Compiled 2026-07-26. Every claim carries its source URL inline.

---

## 0. TL;DR recommendation for Tower

**Primary hero/launch film: 45 seconds.** (Hard ceiling 50s. Do not ship 87s.)
**Social cut: 22 seconds**, 16:9 master + 1:1 crop, burned-in captions, silent-safe.
**Loop cut: 12 seconds**, muted autoplay background loop for the landing-page hero,
with the 45s film behind a click-to-play poster below it.

Rationale in §7. Second-by-second budgets in §8–§10.

---

## 1. Optimal length by surface

### (a) Landing-page hero

Wistia's State of Video (14M+ videos, 100k businesses, 1,300-person survey) is the
biggest public dataset and the direction is monotonic: **the shorter the video, the
higher the engagement rate.**

- Videos **under 1 minute: 50% average engagement rate**; 1–3 min: 46%; 3–5 min: 45%.
  Engagement falls with every length bucket.
  — https://wistia.com/learn/marketing/video-marketing-statistics
  — https://finance.yahoo.com/news/wistias-2025-state-video-report-130000357.html
- The same report cut by coarser buckets: **under 5 min = 47%** (down 10 points YoY),
  **5–30 min = 38%**, **over 30 min = 21%**. Overall engagement hit a four-year low;
  2024 engagement fell 7% vs the prior year.
  — https://www.chiefmarketer.com/wistia-state-of-video-report-engagement-down-content-under-promoted/
- Videos on **landing pages, blog posts and galleries see engagement above 40%**;
  homepages, galleries and product pages are the best-performing placements by play rate.
  — https://wistia.com/learn/marketing/insights-state-of-video-report
- Wistia's older longitudinal study (564,710 videos, 1.3B plays) put the cliff at
  **2 minutes**; the 2023 re-run moved the cliff **to ~60 seconds**. Retention ≈70% for
  sub-2-minute videos, **below 50% past 2 minutes**.
  — https://wistia.com/learn/marketing/optimal-video-length
  — https://wistia.com/learn/marketing/understanding-audience-retention

Practical hero convention that the data supports: **a 10–20s muted autoplay loop** as
background, and any message-carrying video as **click-to-play with a strong poster
frame**, because sound-on autoplay is blocked/restricted on mobile and startles visitors.
Best-performing homepage product demos land **60–90s**; a single-offer hero lands **30–60s**.
— https://sitesplaced.com/blog/cinematic-landing-pages-with-video-backgrounds
— https://swarmify.com/blog/video-landing-page/
— https://demosmith.ai/blog/how-long-should-demo-video-be

Conversion caveat worth knowing so you don't over-optimise for engagement rate: Wistia
found **longer videos convert better per viewer** (30min+: 17% conversion; 3–5min: 5%;
under 3min: 2%) — because the survivors are self-selected buyers. That's an argument for
a *separate* long demo, **not** for making the hype film longer. The hype film's job is
reach and comprehension, not closing.
— https://www.chiefmarketer.com/wistia-state-of-video-report-engagement-down-content-under-promoted/

### (b) X / Twitter

- X's own ad guidance and the 2025–26 spec consensus: **15 seconds or less is ideal**,
  max 2:20; **15–30s gives the best completion rates**, 20–45s still performs.
  Video autoplays **silently** in feed, so the first seconds and captions are decisive.
  — https://quickframe.com/blog/twitter-video-ad-specs
  — https://blog.hootsuite.com/twitter-ads/
  — https://benly.ai/learn/x-ads/x-twitter-ads-formats-specs

### (c) YouTube

- Average retention across all long-form YouTube video is **23.7%**, and **~55% of
  viewers are gone by the 60-second mark**. Only 16.8% of videos clear 50% retention.
  — https://www.retentionrabbit.com/blog/2025-youtube-audience-retention-benchmark-report
- Healthy retention **for videos under 5 minutes is 50–70%** — i.e. short videos are the
  only reliable way to post a good retention graph.
  — https://prepublish.ai/blog/youtube-retention-benchmarks-2026
  — https://humbleandbrag.com/blog/youtube-audience-retention-benchmarks
- Videos where **>65% of viewers pass the 1-minute mark show 58% higher average view
  duration** for the whole remainder — the opening compounds.
  — https://humbleandbrag.com/blog/youtube-audience-retention-benchmarks

For a launch film, YouTube is a *hosting* surface (embeds, "watch the film" links), not a
discovery surface. Post the same 45s master; a sub-60s cut is also Shorts-eligible.

### (d) Product Hunt

- PH autoplays **muted** in the feed. The prevailing playbook: **45–60s**, work with no
  sound, and **show the product doing its most impressive thing in the first 5 seconds**.
  Wider guidance clusters **30–90s**, with 60–90s the common recommendation and 2 minutes
  the absolute ceiling. Products with video rank higher, get more upvotes and more comments.
  — https://www.vibrantsnap.com/blog/product-hunt-launch-video-guide
  — https://demosmith.ai/blog/product-hunt-launch-demo-video
  — https://motionfly.co/blog/product-hunt-launch-checklist

### Cross-surface synthesis

| Surface | Evidence-backed target | Ceiling |
|---|---|---|
| Landing hero (click-to-play) | 30–60s | 90s |
| Landing hero (bg loop, muted) | 10–20s | 20s |
| X / Twitter | 15–30s | 45s |
| YouTube (embed/launch post) | 45–60s | 90s |
| Product Hunt | 45–60s | 90s |

**The overlap of all four is 45–60s.** One master at the low end of that band (45s) plus a
~20s social cut covers every surface without a bespoke edit per platform.

---

## 2. Where drop-off happens, and what must be in the first 3 seconds

- **Nielsen for Meta, 173 Brand Effect studies:** viewers who watched **under 3 seconds
  still delivered up to 47% of total campaign value** (47% ad-recall lift, 32% brand
  awareness, 44% purchase intent). Under 10 seconds delivered **up to 74%** of value.
  Value accrues **from second zero**, not from completion.
  — https://martech.org/even-brief-video-views-drive-brand-lift-facebook-nielsen-study-finds/
  — https://www.marketingdive.com/news/brand-lift-happens-in-less-than-1-second-of-video-study-finds/377333/
- Short-form: **50–60% of all drop-off on YouTube Shorts happens inside the first three
  seconds**; ~70%+ of TikTok viewers decide to stay or go in that window.
  — https://www.opus.pro/blog/ideal-youtube-shorts-length-format-retention
  — https://autofaceless.ai/blog/attention-span-statistics-2026 (aggregator; treat as directional)
- Long-form: **55% of YouTube viewers leave by 0:60.**
  — https://www.retentionrabbit.com/blog/2025-youtube-audience-retention-benchmark-report
- Vidyard (943,305 B2B videos, Jan–Dec 2024): **65% of viewers finish a sub-1-minute
  video; only 20% finish a 20-minute one.** Their explicit guidance: **front-load key
  messages within the first quarter of runtime.**
  — https://www.vidyard.com/business-video-benchmarks/
  — https://www.marketingprofs.com/charts/2023/49949/business-video-benchmarks-retention-rates-by-length

**Cost of a slow open.** A logo sting, a fade-from-black, a "hi, I'm X", or an
establishing desktop shot spends the single most valuable asset you have. Meta's data
says the first 3 seconds carries ~47% of the brand value; Shorts data says up to 60% of
your churn happens there. A 3-second slow open on a 45s film burns ~7% of runtime and a
disproportionate share of total delivered value.

**Rules for seconds 0:00–0:03:**
1. Frame 1 is already the product doing something, in motion. No black, no fade-in, no logo.
2. The strongest visual moment of the whole film should be a candidate for the cold open.
3. One legible super, ≤5 words, stating the category or the promise — because the
   soundtrack may not be playing (§6).
4. No text that requires reading more than ~7 words in those 3 seconds (§5).
5. Logo goes at the **end**, not the start.

---

## 3. Proven structure for a launch film

The consensus arc across launch films and the demo-video literature — hook → problem →
reveal → proof → stakes → CTA — is well supported by the front-loading evidence: the
"reveal" must not sit behind a long problem setup, because Vidyard's front-load rule
(first quarter of runtime) means at 45s **the product must be legible by ~0:11**.
— https://www.vidyard.com/business-video-benchmarks/
— https://demopolish.com/blog/saas-demo-video-best-practices/
— https://levitatemedia.com/learn/best-saas-demo-videos-2026-10-tips-for-creating-outstanding-ones

Percentage budget that survives both 30s and 60s:

| Act | Share | 30s | 60s |
|---|---|---|---|
| Hook (product in motion, cold) | 10% | 0:00–0:03 | 0:00–0:06 |
| Problem / tension | 13% | 0:03–0:07 | 0:06–0:14 |
| Product reveal (name + mark) | 10% | 0:07–0:10 | 0:14–0:20 |
| Proof / demo beats | 40% | 0:10–0:22 | 0:20–0:44 |
| Stakes / payoff line | 17% | 0:22–0:27 | 0:44–0:54 |
| CTA + logo + URL | 10% | 0:27–0:30 | 0:54–1:00 |

Notes that matter more than the grid:
- **Proof is the biggest block at every length.** It is the only act that earns belief.
- **The CTA must hold ≥3s static** so a paused/scrubbed frame still shows the URL.
- **Problem shrinks first** when you cut down; proof shrinks last.

---

## 4. Pacing

- Feature-film ASL has fallen from **8–11s (pre-1960) to 4–6s today**; contemporary
  action sits at **1.7–2.4s** (Mad Max: Fury Road 2.1s, Bourne Supremacy 2.4s,
  Taken 3 / Resident Evil: Apocalypse 1.7s).
  — https://www.filmmakersacademy.com/glossary/average-shot-length-of-films/
  — https://nofilmschool.com/2018/12/how-long-average-shot-lengths-change-how-we-watch-ptas-films
- **Commercials cut far faster than film** — ASLs under 1 second are documented, i.e.
  **60+ cuts per minute**.
  — http://www.cinemetrics.lv/lab.php?ID=165
  — https://www.metafilter.com/90102/Cinemetrics-database-of-Average-Shot-Length

**Targets for a high-energy software promo:**
- **ASL 1.2–2.0s → 30–50 shots per minute.** At 45s that is **~26–35 shots**.
- But screen-recording content has a hard floor that film doesn't: a UI beat needs
  **~1.5–2.5s** to be *comprehended*, not just seen. So run a **bimodal** rhythm:
  fast connective shots at 0.6–1.0s, and **3–5 "hero" UI holds at 2.0–2.5s** where the
  viewer actually reads the interface. Average lands ~1.5s.
- **Cut on the beat.** Pick a track at 120–128 BPM (= 0.5s per beat, 2s per bar) and
  place hero holds on bar lines. This makes the bimodal rhythm feel designed rather than
  erratic.
- **Speed ramps**: use them to *cross* dead time, never to cross information. Ramp
  through cursor travel, window opening, scrolling — then land at 100% on the state
  change you want read. Typical ramp: 400–800% through 1–2s of travel, ~6–10 frames of
  ease-out into the landing.
- **Freeze frames**: reserve for **state changes worth naming** — the moment the badge
  flips to BLOCKED, the moment usage renders. Hold **8–14 frames (~0.3–0.5s)** with the
  super appearing on the freeze, then resume. Two or three per film maximum; more and
  they stop reading as emphasis.
- **Never bounce a failure state.** (Tower's own design law, docs/DESIGN.md: motion =
  state change; failure never bounces.) A block/fault beat should cut hard or hold, not
  spring.

---

## 5. On-screen copy: how much can be read

- **BBC subtitle guideline: 160–180 words per minute ≈ 15 characters/second** for a
  general audience.
  — https://www.clevercast.com/bbc-subtitling-guidelines/
- **Netflix: 20 CPS adult, 17 CPS children** as a maximum.
  — https://www.gothamlab.com/netflix-subtitle-delivery-requirements-complete-guide/
  — https://subhero.io/blog/subtitle-standards-guide
- Editorial rule of thumb for **supers/title cards** (which have no audio to lean on, so
  they need more time than subtitles): leave the card up long enough to **read it twice**
  at 200 wpm; equivalently **3 seconds + 0.5–0.7s per word**.
  — https://www.ssw.com.au/rules/post-production-do-you-give-enough-time-to-read-texts-in-your-videos

**Working rule for this film:**
- Subtitles/captions synced to VO: **up to 15 CPS (~3 words/sec)**, 2 lines max, 42 chars/line.
- **Standalone supers (no VO under them): 2.5 words/second maximum**, and never fewer
  than **1.2s on screen** even for a single word.
- Practical caps: **≤5 words at 0.8s/word for a punchy card; ≤9 words if it holds ≥3s.**
- A super that lands on a freeze frame gets the freeze *plus* the following shot to be read.
- Never put a super and a UI element the viewer must read in the same 2 seconds.

---

## 6. Caption everything

Yes — burned-in, always, on the social cut; toggleable or burned on the hero.

- **Verizon Media / Publicis Media, 5,616 US adults, April 2019: 69% watch video with
  sound off in public**, 25% with sound off in private. **80% are more likely to finish
  a video when captions are available.** **80% of caption users have no hearing
  impairment.** Mobile viewers seeing captions showed an **8% lift in ad recall and 10%
  lift in ad memory quality.**
  — https://www.forbes.com/sites/tjmccue/2019/07/31/verizon-media-says-69-percent-of-consumers-watching-video-with-sound-off/
  — https://www.3playmedia.com/blog/verizon-media-and-publicis-media-find-viewers-want-captions/
  — https://www.streamingmedia.com/Articles/ReadArticle.aspx?ArticleID=131860
- X, Product Hunt and every in-feed placement **autoplay muted by default**, so the
  silent pass is the *default* pass, not the fallback.
  — https://quickframe.com/blog/twitter-video-ad-specs
- Captions are also the most common accessibility feature teams ship first.
  — https://wistia.com/learn/marketing/video-marketing-statistics

**How to caption this specific film:**
- **Burn in** on the social cut (platform caption rendering is unreliable and gets
  cropped); **ship an .srt as well** for YouTube/embeds so the text is indexable.
- Position captions in the **middle-lower third, above the bottom 20%** — the bottom
  strip is covered by platform UI on X and PH.
- Style per docs/DESIGN.md, not per platform default: one weight, one size, solid or
  ~70% scrim behind, no drop shadow, no karaoke word-pop (it competes with the UI motion,
  and "one loudest thing at a time").
- **The film must be fully comprehensible with sound off.** Test: mute it, hand it to
  someone who has never seen Tower, ask what it does. If they can't answer, the supers
  are doing too little.
- Sound design is then pure *lift*, never *load-bearing*.

---

## 7. Why 45 seconds for Tower specifically

You have **87 seconds of real usage footage**. That's a healthy 1.9:1 ratio against a 45s
cut — enough to be selective, which is exactly what a hype cut needs. Shipping the 87s
raw is the failure mode the data warns about:

1. 87s crosses Wistia's **60-second engagement cliff** and lands in a bucket that loses
   ~4 points of engagement vs sub-1-minute, on top of a category-wide four-year low.
   — https://wistia.com/learn/marketing/video-marketing-statistics
2. It crosses the point where **55% of YouTube viewers have already left** (0:60).
   — https://www.retentionrabbit.com/blog/2025-youtube-audience-retention-benchmark-report
3. It exceeds every platform recommendation except the loosest PH one, so you'd be
   re-cutting for X anyway.
4. Vidyard's sub-1-minute **65% completion** is the single cheapest win available here.
   — https://www.vidyard.com/business-video-benchmarks/

45s (not 60s) because: Tower is a **status layer with three legible ideas** — pin the
country (fence), survive the network (weather), watch every agent — plus one payoff.
That's four beats. Four beats at ~8s each plus a 3s hook and a 4s CTA is 39–45s. Padding
to 60s would mean either a fifth idea (dilutes) or slower holds (kills the ASL target
in §4). **45s sits inside the 45–60s overlap band for all four surfaces**, so one master
serves the hero, YouTube and Product Hunt, and only X needs the short cut.

Note on the guard's honesty stance (CLAUDE.md): the film should show a **block happening
and clearing** as a *feature*. That's the stakes beat, and it is the most differentiated
thing in the footage — do not cut it for time.

---

## 8. Primary cut — 45 seconds, second-by-second

Target ~28–32 shots (ASL ~1.5s). Music 124 BPM; bar = 1.94s; hero holds on bar lines.

| Time | Dur | Act | Content | Super (words) | Notes |
|---|---|---|---|---|---|
| 0:00–0:03 | 3.0s | HOOK | Cold open on the menubar radar sweeping, then the badge flipping to a block state. No fade. Frame 1 is motion. | "Your agent just left the country." (6w, 3.0s) | Strongest single frame of the film. Freeze 10f on the flip. |
| 0:03–0:07 | 4.0s | PROBLEM | Fast montage: VPN drops, region mismatch, a Claude turn erroring / retry spinner. 4 shots @ ~1.0s. | "So Claude got confused." (4w, 1.6s) | Ramp through cursor travel. Keep it tense, not comedic. |
| 0:07–0:11 | 4.0s | PROBLEM→ | The consequence, felt: a session stalling, a retry counter climbing. 3 shots. | "You found out later." (4w, 1.6s) | Last beat before the reveal; end on a held, quiet frame. |
| 0:11–0:16 | 5.0s | REVEAL | Tower launches: menubar icon settles, radar locks, popover opens clean. Slower — 2 shots @ 2.5s. | "Tower." (1w, 1.5s) then "A control tower for your Claude agents." (7w, 3.0s) | Product legible by 0:11 = Vidyard's first-quarter front-load rule. Only place the pace drops. |
| 0:16–0:23 | 7.0s | PROOF 1 | **The fence.** Country pin set; egress IP confirmed; badge goes green/confirmed. 4–5 shots, one 2.2s hero hold on the confirmed state. | "Pin it to one country." (5w, 2.5s) | Real UI, real numbers. No mock data. |
| 0:23–0:30 | 7.0s | PROOF 2 | **The weather.** Net fault appears → request held PENDING → clears itself → traffic resumes. 5 shots, hero hold 2.2s on the pending state. | "Bad network? Held, not failed." (5w, 2.5s) | The honesty beat. Freeze 12f on the moment it self-clears. |
| 0:30–0:37 | 7.0s | PROOF 3 | **The watch.** Dashboard/TUI: every running agent, live status, usage. Fast — 6 shots @ ~1.1s, one 2.0s hold on the full agent list. | "Every agent. One glance." (4w, 2.0s) | Show the TUI here — it is the "for developers" signal. |
| 0:37–0:41 | 4.0s | STAKES | Pull back: the whole system running quietly. Radar sweeping. Single shot, ~2s, then one cut. | "Off-country requests never leave." (4w, 2.5s) | The claim you can actually defend. Calm, not loud. |
| 0:41–0:45 | 4.0s | CTA | Wordmark + URL, static, on the mark. | Logo + URL + one line, holds 4.0s static | ≥3s static so a paused frame carries the URL. Last frame = URL. |

Total: **45.0s.** Act shares: hook 7% / problem 18% / reveal 11% / proof 47% / stakes 9% / CTA 9%.
Proof-heavy on purpose (§3) — for a security-adjacent dev tool, demonstration *is* the argument.

**Cut-down order if it runs long:** trim 0:07–0:11 first (problem→), then PROOF 3 shots,
then stakes. Never trim the hook, the reveal legibility, or the CTA hold.

---

## 9. Social cut — 22 seconds (X / Reels / Shorts)

Sits inside X's 15–30s best-completion band. Same master, no new footage.

| Time | Dur | Content | Super |
|---|---|---|---|
| 0:00–0:03 | 3.0s | Identical cold open (badge flips to block). | "Your agent just left the country." |
| 0:03–0:06 | 3.0s | One problem shot + retry spinner. | "Claude didn't notice. Tower did." |
| 0:06–0:09 | 3.0s | Reveal: menubar lock + popover. | "Tower." |
| 0:09–0:13 | 4.0s | Fence: pin country, confirmed. | "Pin it to one country." |
| 0:13–0:17 | 4.0s | Weather: held → self-clears. | "Held, not failed." |
| 0:17–0:19 | 2.0s | Watch: agent list, one fast pan. | "Every agent, one glance." |
| 0:19–0:22 | 3.0s | Wordmark + URL, static. | URL |

Total **22.0s**. Burned-in captions mandatory. Export 16:9 master, 1:1 and 9:16 crops with
the UI re-framed (not letterboxed) — menubar content is small; crop into it rather than
scaling the whole desktop down.

---

## 10. Loop cut — 12 seconds (landing hero background)

Muted, autoplay, `loop playsinline`, ≤4MB, H.264, 1920×1080, poster frame = the confirmed
green state. Content: radar sweep → confirmed badge → one agent-list pan → seamless return
to frame 1. **No text** (the page headline carries the words). Click-to-play card below it
opens the 45s film.
— https://sitesplaced.com/blog/cinematic-landing-pages-with-video-backgrounds
— https://swarmify.com/blog/video-landing-page/

---

## 11. Checklist before export

- [ ] Frame 1 is product in motion. No black, no fade, no logo.
- [ ] Product name legible by 25% of runtime (0:11 at 45s).
- [ ] ASL 1.2–2.0s; 3–5 hero holds at 2.0–2.5s; hero holds on bar lines.
- [ ] Every super ≤2.5 words/sec, ≥1.2s minimum, never over UI the viewer must read.
- [ ] Captions burned in on social; .srt shipped with hero/YouTube.
- [ ] Watched muted end-to-end by someone who's never seen Tower — they can say what it does.
- [ ] CTA holds ≥3s static; final frame is the URL.
- [ ] No bouncing/springy motion on any failure or block state (docs/DESIGN.md).
- [ ] Real UI, real values only — the product's whole pitch is honesty.

---

## Sources

1. https://wistia.com/learn/marketing/video-marketing-statistics — Wistia State of Video (14M+ videos, 100k businesses, 1,300 survey respondents)
2. https://wistia.com/learn/marketing/insights-state-of-video-report
3. https://www.chiefmarketer.com/wistia-state-of-video-report-engagement-down-content-under-promoted/
4. https://finance.yahoo.com/news/wistias-2025-state-video-report-130000357.html
5. https://wistia.com/learn/marketing/optimal-video-length
6. https://wistia.com/learn/marketing/understanding-audience-retention
7. https://www.vidyard.com/business-video-benchmarks/ — Vidyard, 943,305 B2B videos, 2024
8. https://www.marketingprofs.com/charts/2023/49949/business-video-benchmarks-retention-rates-by-length
9. https://martech.org/even-brief-video-views-drive-brand-lift-facebook-nielsen-study-finds/ — Nielsen/Meta, 173 Brand Effect studies
10. https://www.marketingdive.com/news/brand-lift-happens-in-less-than-1-second-of-video-study-finds/377333/
11. https://www.retentionrabbit.com/blog/2025-youtube-audience-retention-benchmark-report
12. https://prepublish.ai/blog/youtube-retention-benchmarks-2026
13. https://humbleandbrag.com/blog/youtube-audience-retention-benchmarks
14. https://www.opus.pro/blog/ideal-youtube-shorts-length-format-retention
15. https://quickframe.com/blog/twitter-video-ad-specs
16. https://blog.hootsuite.com/twitter-ads/
17. https://benly.ai/learn/x-ads/x-twitter-ads-formats-specs
18. https://www.vibrantsnap.com/blog/product-hunt-launch-video-guide
19. https://demosmith.ai/blog/product-hunt-launch-demo-video
20. https://motionfly.co/blog/product-hunt-launch-checklist
21. https://demosmith.ai/blog/how-long-should-demo-video-be
22. https://sitesplaced.com/blog/cinematic-landing-pages-with-video-backgrounds
23. https://swarmify.com/blog/video-landing-page/
24. https://demopolish.com/blog/saas-demo-video-best-practices/
25. https://levitatemedia.com/learn/best-saas-demo-videos-2026-10-tips-for-creating-outstanding-ones
26. https://www.forbes.com/sites/tjmccue/2019/07/31/verizon-media-says-69-percent-of-consumers-watching-video-with-sound-off/ — Verizon Media/Publicis, 5,616 US adults, April 2019
27. https://www.3playmedia.com/blog/verizon-media-and-publicis-media-find-viewers-want-captions/
28. https://www.streamingmedia.com/Articles/ReadArticle.aspx?ArticleID=131860
29. https://www.clevercast.com/bbc-subtitling-guidelines/ — BBC 160–180 wpm ≈ 15 CPS
30. https://www.gothamlab.com/netflix-subtitle-delivery-requirements-complete-guide/ — Netflix 20 CPS adult / 17 CPS children
31. https://subhero.io/blog/subtitle-standards-guide
32. https://www.ssw.com.au/rules/post-production-do-you-give-enough-time-to-read-texts-in-your-videos — "read it twice" rule
33. https://www.filmmakersacademy.com/glossary/average-shot-length-of-films/
34. https://nofilmschool.com/2018/12/how-long-average-shot-lengths-change-how-we-watch-ptas-films
35. http://www.cinemetrics.lv/lab.php?ID=165 — Cinemetrics
36. https://www.metafilter.com/90102/Cinemetrics-database-of-Average-Shot-Length
37. https://www.socialinsider.io/social-media-benchmarks/social-media-video-statistics — Socialinsider, 11M IG / 3M FB / 2M TikTok / 67K LinkedIn posts, Sep 2025

**Source-quality note:** items 1–10, 15–16, 26–36 are primary datasets, platform docs or
first-party research. Items 11–14, 17–25 are secondary aggregators used only for
directional platform conventions; where a number from those appears above it is labelled
as consensus/guidance, not measurement.

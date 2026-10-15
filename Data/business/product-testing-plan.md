# Product Testing Plan — SimplyBilly

- **Reset:** 2026-10-11 (America/Chicago). One topic, not four.
- **Roadmap image:** `Data/business/product-testing-roadmap.png` (source: `product-testing-roadmap.html`)

## Mission

**I test products and publish a detailed, honest assessment of every one — any category, no hype.**

Games, tech, skincare, pop-culture merch, Amazon buys: all fair game *if* they get tested and assessed. Amazon Influencer is not a lane anymore; written Amazon buyer reviews (~20 so far) are practice reps.

## The one rule: every test = a detailed assessment

A detailed assessment means the claims were actually tested, over real time, with notes and something measurable — and the verdict follows from the results, not the hype. A dud still gets a full assessment, paired with something that actually works.

### Assessment template (copy per product)

```markdown
## Assessment: <Product name>
- **Price paid / where bought / date:** $__ · <store> · YYYY-MM-DD   (or: gifted by <brand>)
- **Category:**
- **Claims tested:** (copy the brand's exact claims)
  1.
  2.
  3.
- **Test method:** how I tested each claim (setup, conditions, what I compared against)
- **Duration:** __ days / __ uses
- **Day-by-day notes:**
  - Day 1:
  - Day 3:
  - Day 7:
  - (add days as needed)
- **Measurable results:** numbers, photos, timings, before/after — per claim: ✅ held · ⚠️ partly · ❌ failed
- **Pros:**
- **Cons:**
- **Who it's for:**
- **Who it's NOT for:**
- **Verdict + score (__/10):** one line, then 2–3 sentences of reasoning tied to the results above
- **If it's a dud, what works instead:**
- **Disclosure:** bought with my own money / gifted by __ / paid by __ · affiliate link: yes/no
```

Bolt helpers: `bolt manage add "Item" --lane product --status testing` (start) · `bolt manage note "Item" --day N --text "..."` (daily notes) · `bolt manage draft "Item" --format short` (package the short).

## Phases

| # | Phase | Window | Goal | Exit criteria | First action |
|---|-------|--------|------|---------------|--------------|
| 1 | **Foundation** | Oct 11 – Nov 4, 2026 | Template in use; first assessments of things I already own | 3 detailed assessments complete; each posted (with my approval) as 1 short + written version | Pick 3 owned products and add them to Bolt |
| 2 | **Proof / Portfolio** | Nov 5, 2026 – Jan 31, 2027 | Steady, boring consistency | ~10 public assessments total; simple portfolio page linking all of them | Make the portfolio page with the first 3 |
| 3 | **Credibility** | Feb – Apr 2027 | Outside proof that my reviews are trusted | Joined at least one product-testing / honest-review program or panel; affiliate links live with disclosure; decide on revisiting Amazon Influencer with the portfolio | Apply to 1–2 consumer product-testing panels |
| 4 | **Outreach** | May – Jul 2027 | Brands send units under honest-review terms | Media kit done; first gifted unit received + assessed honestly | Build a 1-page media kit (`bolt sponsors pitch` for drafts) |
| 5 | **Career** | Aug 2027 → | Get paid to test | First paid review, UGC/testing contract, retainer, or tester job | List 5 brands/companies I'd want to test for |

**Phase 1 target, restated:** the old target (20 shorts + 4 long-form by Nov 4) is set aside for product testing. New target: **3 detailed assessments by Nov 4**, each with 1 short. Stretch: 1 long-form review. Quality of the assessment beats count.

Programs: Amazon Vine is invite-only (Amazon picks reviewers, largely from helpful buyer reviews), so it's a "keep writing great Amazon reviews" goal, not an application. Other credibility routes, described generically: brand tester/ambassador sign-ups, independent consumer product-testing panels, and affiliate programs (Amazon Associates `billycarter-20` if still active) — always disclosed.

## Weekly rhythm (4–5 days, low social load)

- **Mon — Pick + set up (20 min):** choose the product, copy the template, list the claims, `bolt manage add`.
- **Tue–Thu — Test + note (5–10 min/day):** use it, `bolt manage note --day N`. Photos/clips of hands + product only is fine (no face needed).
- **Fri — Write the verdict (30–45 min):** finish the assessment; `bolt manage draft --format short`.
- **Sat — Approve + post 1 thing** (Bolt never posts without my OK). Comments: optional, batch once a week, or skip.
- **Sun — 10-min look back:** `bolt log-perf`, pick next week's product. Rest otherwise.

## Metrics that matter

| Phase | Watch | Ignore for now |
|-------|-------|----------------|
| 1 Foundation | Assessments completed (target 3) | Views, followers |
| 2 Proof | Assessments published (~10), weeks in a row with one posted | Viral spikes |
| 3 Credibility | Programs joined, Amazon review helpful votes, affiliate clicks | Revenue |
| 4 Outreach | Pitches sent, replies, gifted units | Follower count |
| 5 Career | Paid deals / contracts, income per assessment | Vanity metrics |

## Guardrails

- **Honesty first:** never present a hype product as if it works. Duds get a full honest assessment + a "what works instead" pick.
- **Disclosure (FTC):** say clearly when something is gifted, paid, or an affiliate link (#ad / #gifted / "affiliate link"), up front, in the post itself.
- **Gifted ≠ positive:** only accept units under honest-review terms; no brand approves my verdict.
- **Approval:** nothing posts without my approval. TikTok auto-publish stays paused.
- **Protect energy:** one product at a time. Engagement is optional; family privacy is fine — hands-only/product-only content counts.
- **No same-day Amazon Influencer reapply.** Revisit only with a real portfolio (Phase 3+).

## This week (Oct 11–17, 2026)

1. **Pick 3 products I already own** (one can be a dud) and add them: `bolt manage add "Item" --lane product --status testing`.
2. **Start product #1:** fill in price/where bought/claims in the template and log Day 1 with `bolt manage note "Item" --day 1 --text "..."`.
3. **Friday:** write the first verdict + score, then `bolt manage draft "Item" --format short` and approve it when ready.

**If only one thing happens:** do step 1.

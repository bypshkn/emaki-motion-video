# Licensing: what may go into a film we sell

This is a working checklist, not legal advice: when a case is unclear or the stakes are high, the
user asks a lawyer. Films made with this skill are often sold to clients and published under
their names. Every file in a
film that we did not make in code is someone's property. A file with no license in a client ad
is the most expensive defect we can ship: the client takes it down, or a rights holder comes
after them. QA cannot see rights in pixels, so the project keeps a record: the rights ledger.

What happened on a client ad, found after approval and before publishing: 86 photos of 41 lots
from two auction websites and both sites' logos were collected "for the mockup" and ended up in
the approved film. One site's notice says its content is for personal, non-commercial use only,
any other use needs its written consent, and its trademarks may not be used. The music was
licensed, but no proof was saved.

## The rule

1. A file enters `assets/` or `fonts/` only from an allowed source (table below).
2. It gets a row in `licenses/assets.yaml` at that moment: source page, author, license, date.
   Field guide: `assets/templates/licenses.yaml`. `$MV licenses <dir>` adds stubs for files with
   no row; fill them in, never leave `license: unknown` in a commercial film.
3. Everything else is a reference: it lives in `refs/`, is analysed, and is rebuilt in code.
   QA `rights` blocks any file from `refs/` that shows up on screen.
4. Before the handover `$MV licenses <dir>` writes `licenses/README.md` (English, for the
   client), `copy-for-approval.md` and copies the license snapshots. The folder goes to the
   client with the film.

`brief.yaml use`: `commercial` (default: sold, published or shown to a client) or `internal`
(a test that never leaves the team). On a commercial film QA `rights` fails the final for a
file with no row or a blocked row and warns about open gaps; on an internal one it only warns.

## Allowed sources

| source | covers | conditions | save in licenses/ |
|---|---|---|---|
| Made in code | sound from `scripts/audio`, every vector, UI rebuilt as vectors | none; a row with `files: []` and `license: own` names the generator if the README should say so | nothing |
| The user's own files | photos they took, their recordings, their voice | `license: own`, say who made it in `note`. A photo of their car on an auction site is the auction's photo, not theirs | nothing |
| The client's files | logo, brand fonts, product screens, photos, footage | `license: client`. Their written OK that they own it and allow its use in the film. A brand font bought for desktop or web may not cover video: ask | the email or message |
| Pixabay | music, sound effects, photos, video | Pixabay Content License: client videos and ads are allowed when the file is part of a larger work, not sold or shared on its own. Trademarks, logos or recognisable people inside a file may need extra consent. Only files downloaded from pixabay.com | a screenshot or PDF of the page; the License Certificate for a track with the shield icon |
| Unsplash | photos | Unsplash License: commercial use without credit. Not for selling the photo unaltered or building a competing photo service. Recognisable people may need a model release. Check unsplash.com/license | a screenshot of the page |
| Generated voice | `assets/voice.wav` from `$MV tts` (Google Cloud Text-to-Speech, Chirp 3 HD library voice) | `license: google-tts`; the row is added by `$MV tts`. The audio is ours: Generated Output is Customer Data and Google claims no ownership; commercial use and ads are allowed, no credit needed (terms read 2026-10-19, `assets/licenses/google-tts-terms-summary_2026-10-19.md`). Not in a film for children or teenagers; never passed off as a real person or a human recording; not in unsolicited mass mailings; never used to train another voice. The client should know: a library voice is not exclusive, and Google gives no indemnity for it. The script lines we wrote go to `copy-for-approval.md` | nothing (the terms summary is copied in) |
| Free fonts | OFL, Apache, Ubuntu Font Licence, DejaVu | free to use in a film. Fonts that declare it inside the file pass without a row | nothing |
| Anything else | | only with written permission (`license: permission`) or a license you read and record (`license: other` + `license_url`, then `status: ok`) | the permission or the license text |

Never, whatever the brief says: photos, video or logos from other websites (auctions,
marketplaces, social networks, search results, competitors, stock sites with watermarks),
screenshots of other companies' products, AI-generated pictures or video (this skill draws in
code), third-party logos and trademarks without written permission (name them in the copy
instead). If the client wants such a file in the film, the client gets the permission first.

## Music and Content ID

- Some Pixabay authors register their tracks in YouTube Content ID. The track page shows a
  shield icon. Their tracks are still free to use, but uploads get automated claims.
- For a client ad prefer a track without the shield. An author who lists a collecting society
  (BMI, ASCAP and the like) on the profile manages the rights actively: take it as a sign to
  expect claims.
- Record `content_id: yes | no | unknown` in the row. For a track with the shield, the License
  Certificate (Download menu on the track page, needs a login) is the proof for a dispute.
  You cannot log in: list it for the user.
- A Content ID claim is not a copyright strike: it can take the ad revenue or mute the sound, it
  does not touch the channel. The dispute goes with the certificate or the track link, the
  license link and how the music is used. A second-level appeal only when sure: Pixabay warns
  that a rejected appeal can turn into a strike. Instagram and Facebook: the same data; the
  platform may contact info@pixabay.com.
- Tell the user whose account will publish the film (`brief.yaml publisher`): claims go there.

## Copy and claims on screen

Prices, ratings, review quotes and every line we wrote are statements in the client's ad. QA
lists invented copy as `[DEMO COPY]`; `$MV licenses` writes all of it into
`licenses/copy-for-approval.md` for the client to approve word for word. Ratings and prices
change: the client checks them on the day of publication. Product screens show demo data only,
never a real user; features not released yet need the client's OK (a row with `files: []`).

## What the user collects by hand

You cannot log in to stock sites or write to the client. After `$MV licenses`, list for the user:
the certificates and page screenshots to save, the client approvals to get, the blocked rows and
their `fix`. Say plainly when a film is not cleared for publication.

## Out of scope

Who owns the finished film, what the client may do with it and how AI-made parts are treated by
copyright law are contract questions for the user and their lawyer, not for this skill. The
files in `assets/licenses/` are our own summaries with the date the source was read, not the
binding text and not legal advice; the binding text is always the current one on the source's
site.

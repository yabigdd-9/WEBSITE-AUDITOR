# Homepage meta-description fix — proposed, not applied

The independent source check in
`docs/verification/2026-11-16-meta-description.json` found no standard description
on `https://davidrobertson.co.nz/`, while the checked interior, exterior,
commercial and roof painting pages already had usable descriptions. Their
metadata should not be replaced for this finding. An Open Graph description
already exists and is separate from the standard description tag.

This packet changes one homepage field. It does not claim a ranking, traffic,
conversion or revenue improvement. No live website has been changed.

## Apply after the site owner grants access

1. Recheck the homepage's HTML source before applying: if a valid standard
   description has since been added, stop and review it rather than overwrite it.
2. In the site's existing CMS/SEO settings for the homepage, save the plain text
   in `description.txt` in its meta-description field. Do not paste the HTML
   snippet into a text field. Do not install another SEO plugin for this change.
3. For a source-controlled HTML site instead, the site maintainer can add the
   single tag in `meta-description.html` to the homepage's `<head>`. Do not use
   both methods or create a second standard description tag.
4. Save/publish through the owner's normal reviewed workflow and clear relevant
   page/CDN caches if the site uses them.
5. Fetch the homepage again and verify exactly one non-empty standard
   `meta[name="description"]` in the returned HTML matches the approved copy.
   Check the existing Open Graph description and the four service-page
   descriptions remain intact. Search snippets may differ and may update later.

## Rollback

Restore the previous homepage description field or remove only the newly added
standard tag, then clear the same caches and recheck the source. Preserve the
existing Open Graph and service-page tags.

`manifest.json` records the original page hash, observation time and unapplied
status. No client login, site owner authorization or production deployment access
is available in this workspace. Keep `verified_fixed=false` until a fresh source
check proves the approved live change.

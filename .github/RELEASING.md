# Releasing

A release is a tag on master. Each one gets a GitHub release with its notes,
and once Zenodo is linked, a DOI, so a paper can cite the exact version it
used (the Docker image of that commit is `ghcr.io/jameskress/visualization_vignettes:<short sha>`).

## One-time setup (James)

1. Sign in to <https://zenodo.org> with GitHub, open **GitHub** in the account
   menu, and switch on `jameskress/Visualization_Vignettes`.
2. Zenodo then archives every published GitHub release and mints a DOI for it,
   reading `CITATION.cff` for the authors, title, license and keywords. There
   is no `.zenodo.json`, so `CITATION.cff` is the one place to keep that
   metadata.
3. After the first DOI exists, add its concept DOI (the one that always points
   at the newest version) to `CITATION.cff` (`doi:`) and as a badge in
   `README.md`.

## Each release

1. Choose the version ([Semantic Versioning](https://semver.org/spec/v2.0.0.html)):
   a new major version when results or record schemas stop being comparable
   with the previous release, a minor version for new features, a patch for
   fixes only.
2. On a branch, in one PR:
   - in `.github/CHANGELOG.md`, rename `## [Unreleased]` to
     `## [X.Y.Z] - YYYY-MM-DD` and start a new empty `## [Unreleased]` above it;
   - in `CITATION.cff`, set `version: X.Y.Z` and `date-released: YYYY-MM-DD`.
   - bring the changelog's highlights up to the last merged PR.
3. After that PR merges and master's CI is green, tag the merge commit and push
   the tag:

   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z" <merge commit>
   git push origin vX.Y.Z
   ```

4. `.github/workflows/release.yml` checks that `CITATION.cff` matches the tag
   and that the changelog has the section, then publishes the release with that
   section as its notes. Zenodo picks the release up within minutes. If no DOI
   appears and Zenodo's GitHub page lists the release as failed, re-run it from
   there. If the page does not list the release at all, Zenodo never received
   it: contact Zenodo support with the repository and the tag.

Tags such as `baselines/...` are not releases; the workflow only reacts to
`vX.Y.Z`.

# Dev container

This folder opens the repository inside the project's published Docker image
(`ghcr.io/jameskress/visualization_vignettes:latest`): ParaView 6.2.1 with
Catalyst, ADIOS2, Ascent, Open MPI and everything the Gray-Scott miniapp
needs. VisIt is not in the image, so the VisIt vignettes do not run here.

## Opening it

* **GitHub Codespaces:** use the "Open in GitHub Codespaces" badge in the main
  [README](../README.md#getting-started), or Code > Codespaces > Create on
  GitHub. Pick the **4-core** machine (16 GB memory, 32 GB disk), which the
  configuration asks for; the 2-core machine was not tried.
* **VS Code Dev Containers:** with Docker running, open the folder and choose
  "Reopen in Container". The first open pulls the image (about 4.5 GB).

When the container is created, `post-create.sh` builds the miniapp from this
checkout into `Miniapps/gray-scott/build/devcontainer/` (under a minute on 4
cores), so what you run is what you edited.

## Things to try

Run a ParaView vignette; the screenshot lands in
`ParaView_Vignettes/ex01_pvScreenshot/output/`:

```bash
pvbatch --force-offscreen-rendering ParaView_Vignettes/ex01_pvScreenshot/ex01_pvScreenshot.py
```

Run the miniapp with Catalyst on 2 ranks; the frames land in `datasets/`
under the run folder:

```bash
mkdir -p ~/gs-run && cd ~/gs-run && cp /app/install/*.json /app/install/*.py .
mpirun -np 2 /workspaces/Visualization_Vignettes/Miniapps/gray-scott/build/devcontainer/gray-scott --settings-file=settings-catalyst-insitu.json
```

The workspace path above is the Codespaces one; in VS Code it is the folder
you opened. The [build and run guide](../Miniapps/gray-scott/docs/build-and-run-guide.md)
covers the other backends and settings.

## Why the settings in `devcontainer.json`

`devcontainer.json` is plain JSON (the repository's JSON check rejects
comments), so the reasons live here:

* `remoteUser: vizuser` is the image's own user. For a plain `docker run`,
  the image's entrypoint remaps vizuser to `HOST_UID`; here the Dev Containers
  tooling does the same job with `updateRemoteUserUID`, which matches
  vizuser's UID to the owner of the workspace on Linux hosts.
* `hostRequirements` asks Codespaces for the 4-core machine (16 GB, 32 GB
  disk). The image is about 12 GB unpacked; with 4 CPUs the post-create build
  took 42 s and a 2-rank Catalyst run peaked near 0.6 GB per rank in a local
  check. The 2-core machine (8 GB) was not tried, so this is headroom, not a
  measured minimum.
* `postCreateCommand` builds this checkout's miniapp, so edits in the
  workspace are what runs; the image's own prebuilt copy stays in
  `/app/install`.

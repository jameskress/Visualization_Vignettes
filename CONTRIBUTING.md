# Contributing to KAUST Visualization Vignettes

First off, thank you for considering contributing! This repository is an effort to create a "cookbook" of examples that help KAUST researchers and others around the world effectively use visualization tools like ParaView and VisIt on our HPC resources. We also work to evangelicalize in situ, and provide an in situ app and eamples to help inform and teach others. Your contributions make this resource more powerful and useful for everyone.

We welcome contributions of all kinds, from fixing typos to adding brand-new visualization examples.

***

## Code of Conduct

To ensure a welcoming and positive environment, we expect all contributors to adhere to a code of conduct.

*[Our Code of Conduct](CODE_OF_CONDUCT.md)*

***

## How Can I Contribute?

There are several ways you can contribute to this project:

* **Reporting Bugs:** If you find an error in a script or a mistake in the documentation, please let us know.
* **Suggesting Enhancements:** If you have an idea for a new vignette, a better way to explain a concept, or a feature to add to an existing example, we'd love to hear it.
* **Submitting a Merge Request:** If you want to directly contribute code, documentation, or new examples, this is the way to go.

### Using GitLab Issues

For reporting bugs or suggesting enhancements, the best place is the [GitLab Issue Tracker](https://gitlab.kitware.com/jameskress/KAUST_Visualization_Vignettes/-/issues).

* **Check existing issues** first to see if someone has already reported your issue or suggested your idea.
* **Be descriptive:** For bug reports, please include the HPC system (e.g., Ibex, Shaheen), the module versions you were using, steps to reproduce the error, and any error messages. For enhancement suggestions, clearly explain the problem you're trying to solve and how your idea helps.

***

## Your First Code Contribution

Ready to add or modify a vignette? Here is the standard workflow for submitting your changes.

### 1. Fork and Clone the Repository

1.  **Fork** this repository on GitLab to create your own personal copy.
2.  **Clone** your fork to your local machine or a suitable location on a KAUST system:
    ```bash
    git clone [https://gitlab.kitware.com/YOUR-USERNAME/KAUST_Visualization_Vignettes.git](https://gitlab.kitware.com/YOUR-USERNAME/KAUST_Visualization_Vignettes.git)
    cd KAUST_Visualization_Vignettes
    ```

### 2. Create a New Branch

Create a descriptive branch name for your work. This keeps your changes organized and separate from the `master` branch.
```bash
# Example for a new ParaView vignette for oceanography data
git checkout -b feature/paraview-ocean-slice

# Example for fixing a bug in a VisIt script
git checkout -b fix/visit-script-path-error
```

### 3. Make Your Changes

This is where you'll add your new scripts, update documentation, or fix bugs.

**Guidelines for a Good Vignette:**

* **Self-Contained:** If possible, place your new example in its own directory (e.g., `ParaView_Vignettes/MyNewExample/`).
* **Add a `README.md`:** Every new vignette directory should contain a `README.md` file that explains:
    * What the vignette demonstrates.
    * Any prerequisite data or modules needed.
    * Clear, step-by-step instructions on how to run the example.
* **Comment Your Code:** Whether it's a Python script for `pvpython` or a SLURM batch script, add comments to explain complex or non-obvious parts.
* **Use Existing Conventions:** Look at the other vignettes to see the established structure and style.

### 4. Commit and Push Your Changes

Commit your changes with a clear and descriptive message.

```bash
git add .
git commit -m "feat: Add new ParaView vignette for 3D slicing of ocean data"
git push origin feature/paraview-ocean-slice
```

### 5. Open a Merge Request

1.  Go to the [KAUST Visualization Vignettes repository on GitLab](https://gitlab.kitware.com/jameskress/KAUST_Visualization_Vignettes).
2.  You will see a prompt to create a Merge Request from your recently pushed branch.
3.  Fill out the Merge Request template:
    * Give it a clear title.
    * In the description, explain *what* you changed and *why*.
    * If your MR resolves an existing issue, link to it (e.g., "Closes #12").
4.  Submit the Merge Request. A maintainer will review your contribution, provide feedback, and merge it when it's ready.

Thank you for helping make scientific visualization more accessible!
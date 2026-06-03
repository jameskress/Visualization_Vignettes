# In Situ Visualization Vignettes at KAUST

Welcome to the KAUST In Situ Vignettes! This repository serves as a guide and resource for integrating and utilizing *in situ* visualization and analysis with your simulations. 

## Why Use In Situ Visualization?
As simulation sizes and data output grow, writing all data to disk is increasingly becoming a major bottleneck. *In situ* visualization tackles this by processing data while the simulation is running in memory. Key benefits include:
- **Faster simulations & more throughput:** Eliminates I/O wait times, allowing your simulation to run significantly faster.
- **Increased simulation resolution:** Run at higher temporal and spatial resolutions since you aren't bottlenecked by disk storage limits.
- **Keep only what you need:** Extract features, generate images, or save reduced datasets on the fly.
- **Reduced I/O helps the community:** Less strain on shared supercomputing file systems benefits all users on the cluster.
- **Optimized performance:** Reduced storage requirements keep overall system and simulation performance highly optimal.

---

## Featured: The Gray-Scott Miniapp
**[Explore the Miniapp Here](https://github.com/jameskress/Visualization_Vignettes/tree/master/Miniapps/gray-scott)**

We are actively expanding our *in situ* support across multiple frameworks. To demonstrate this, we have developed a detailed 3D reaction-diffusion miniapp (Gray-Scott). This single repository provides a working example of how to instrument a simulation to concurrently use **ParaView Catalyst**, **Ascent**, and **ADIOS2**. It serves as an excellent starting point for researchers looking to study true *in situ* integrations before adding them into their own codebases.

---

## In Situ Capabilities & Supported Options at KAUST

### 1. Inshimtu
Developed by the KAUST Visualization Core Lab (KVL), Inshimtu is a lightweight *in situ* ‘shim’ designed for existing, unmodified simulations.
- Works directly with files currently written by the simulation.
- Leverages Catalyst and ParaView vis-pipelines.
- Provides a very low barrier to entry.
- Great for trying out *in situ* capabilities without the heavy commitment of a full bespoke code integration.
- **Read the Kitware Article:** [Cyclone Chapala Simulation with ParaView Catalyst through KAUST's Inshimtu Library](https://www.kitware.com/cyclone-chapala-simulation-with-paraview-catalyst-through-kaust-imshimtu-library/)
- **Repository:** [Inshimtu-basic on GitHub](https://github.com/kaust-vislab/Inshimtu-basic)

### 2. ParaView Catalyst
Directly integrate ParaView's powerful visualization and analysis functionalities into your simulation code. Catalyst processes data in memory, meaning you can configure complex visualization pipelines without writing large data streams to disk.
- [ParaView Catalyst Documentation](https://catalyst-in-situ.readthedocs.io/en/latest/index.html)
- **Video Resource:** Check out KVL's comprehensive workshop on basic Catalyst usage: [Scientific Visualization 210: ParaView ~ In Situ Visualization using Catalyst](http://www.youtube.com/watch?v=oMudj6EUy3g).

### 3. Ascent
Ascent is a many-core capable, flyweight *in situ* visualization and analysis infrastructure. It is highly optimized for modern HPC architectures and requires minimal overhead.
- [Ascent Documentation](https://ascent.readthedocs.io/en/latest/)

### 4. ADIOS2
More than just an *in situ* tool, ADIOS2 is a full-scale data management framework. It is highly effective at aiding in better I/O performance, enabling *in situ* workflows, in-transit visualization, and data reduction.
- [ADIOS2 Documentation](https://adios2.readthedocs.io/en/latest/)

### 5. VisIt Libsim
Similar to Catalyst but native to the VisIt ecosystem, Libsim allows you to tightly couple VisIt's analysis tools directly to your simulation code for live processing.
- [VisIt In Situ Tutorial](https://www.visitusers.org/index.php?title=VisIt-tutorial-in-situ)

### 6. VTK-m
VTK-m is a scientific visualization toolkit designed specifically for emerging multi-core and many-core processor architectures. It serves as the heavy-lifting backbone for tools like Ascent, but can also be used independently alongside other libraries to enable highly optimized *in-transit* visualization.
- [VTK-m Documentation](https://m.vtk.org/)

---
*For more information or assistance with implementing these tools in your workflow, please reach out to the KAUST Visualization Core Lab.*

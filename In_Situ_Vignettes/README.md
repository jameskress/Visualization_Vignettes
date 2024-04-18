# In Situ Vignettes

Work in progress

## Why Use In Situ Visualization
- Faster simulations/More simulations
- Increase simulation resolution (time, spatial)
- Keep what you need
- Reduced I/O helps other users too
- Reduced storage keeps performance optimal
- Faster simulations/More simulations
- Increase simulation resolution (time, spatial)
- Keep what you need
- Reduced I/O helps other users too
- Reduced storage keeps performance optimal


## In Situ Options at KAUST

### Inshimtu
KVL has developed Inshimtu
- An in situ ‘shim’
- Designed for existing, unmodified simulations
- Works with files written by simulation
- Uses Catalyst and ParaView vis-pipelines
- Low barrier to entry
- Try-out in situ without commitment of creating a true in situ integration

**Check out an article written with Kitware on the use of Inshimtu**
[Inshimtu Article](https://www.kitware.com/cyclone-chapala-simulation-with-paraview-catalyst-through-kaust-imshimtu-library/)


**Check out the Inshimtu Repo**
[Inshimtu Repo](https://github.com/kaust-vislab/Inshimtu-basic)


### ParaView Catalyst

## Other options for Bespoke In Situ
If you are looking for a true in situ integration there are multiple options available

1. ADIOS2 
    - A full data management solution. 
    - Can aid in better I/O performance, in situ, data reduction
    - https://adios2.readthedocs.io/en/latest/

2. ParaView Catalyst / VisIt Libsim 
    - Directly integrate ParaView of VisIt functionality into your simulation code
    - https://catalyst-in-situ.readthedocs.io/en/latest/index.html
    - https://www.visitusers.org/index.php?title=VisIt-tutorial-in-situ

3. Ascent
    - Ascent is a many-core capable flyweight in situ visualization and analysis infrastructure
    - https://ascent.readthedocs.io/en/latest/

4. VTK-m
    - VTK-m is a toolkit of scientific visualization algorithms for emerging processor architectures (many-core extension of VTK)
    - It is used by Ascent, but can be used with other libraries to enable in transit visualization
    - https://m.vtk.org/


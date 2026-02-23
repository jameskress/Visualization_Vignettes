cmake \
-Dcatalyst_DIR=/scratch/kressjm/Visualization_Vignettes/software/paraview-build/install/lib/cmake/catalyst-2.0/ \
-DVTK_DIR=/scratch/kressjm/Visualization_Vignettes/software/paraview-build/install/lib/cmake/paraview-6.0/vtk \
-DAscent_DIR=/scratch/kressjm/Visualization_Vignettes/software/ascent/build/install/ascent-checkout/lib/cmake/ascent \
-DADIOS2_DIR=/scratch/kressjm/Visualization_Vignettes/software//adios2-install/lib64/cmake/adios2 \
-Dkombynelite_DIR=/scratch/kressjm/Visualization_Vignettes/software/kombynelite-v1.5-linux-x86_64/lib/cmake/kombynelite \
-DENABLE_TIMERS=1 \
-DCMAKE_BUILD_TYPE=RelWithDebInfo \
-DENABLE_ASCENT=ON \
-DENABLE_CATALYST=ON \
-DENABLE_ADIOS2=ON \
-DENABLE_KOMBYNELITE=OFF \
-DCMAKE_INSTALL_PREFIX=../install \
-DBUILD_ANALYSIS_READER=ON \
../

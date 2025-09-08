~/packages/cmake-3.27.5-linux-x86_64/bin/cmake \
-Dcatalyst_DIR=/home/kressjm/packages/paraview-src/build_6.0.0/install/lib/cmake/catalyst-2.0 \
-DVTK_DIR=/home/kressjm/packages/paraview-src/build_6.0.0/install/lib/cmake/paraview-6.0/vtk \
-DAscent_DIR=/home/kressjm/packages/ascent/build/install/ascent-checkout/lib/cmake/ascent \
-DADIOS2_DIR=/home/kressjm/packages/KAUST_Visualization_Vignettes/adios2-install/lib/cmake/adios2 \
-Dkombynelite_DIR=/home/kressjm/packages/kombynelite-v1.5-linux-x86_64/lib/cmake/kombynelite \
-DFides_DIR=/home/kressjm/packages/KAUST_Visualization_Vignettes/fides/fides-install/lib/cmake/fides \
-DViskores_DIR=/home/kressjm/packages/KAUST_Visualization_Vignettes/viskores/viskores-install/lib/cmake/viskores-1.0 \
-DENABLE_TIMERS=1 \
-DCMAKE_BUILD_TYPE=DEBUG \
-DENABLE_ASCENT=ON \
-DENABLE_CATALYST=ON \
-DENABLE_ADIOS2=ON \
-DENABLE_KOMBYNELITE=OFF \
-DCMAKE_INSTALL_PREFIX=../install \
-DBUILD_ANALYSIS_READER=ON \
../



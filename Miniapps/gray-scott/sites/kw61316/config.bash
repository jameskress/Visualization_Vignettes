~/packages/cmake-3.27.5-linux-x86_64/bin/cmake \
-Dcatalyst_DIR=/home/kressjm/packages/paraview-src/build_5.13.3/install/lib/cmake/catalyst-2.0 \
-DVTK_DIR=/home/kressjm/packages/paraview-src/build_5.13.3/install/lib/cmake/paraview-5.13/vtk \
-DAscent_DIR=/home/kressjm/packages/ascent/build/install/ascent-checkout/lib/cmake/ascent \
-DADIOS2_DIR=/home/kressjm/packages/KAUST_Visualization_Vignettes/adios2-build \
-DENABLE_TIMERS=1 \
-DCMAKE_BUILD_TYPE=DEBUG \
-DENABLE_ASCENT=ON \
-DENABLE_CATALYST=ON \
-DENABLE_ADIOS2=ON \
-DCMAKE_INSTALL_PREFIX=../install \
../



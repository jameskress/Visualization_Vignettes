#ifndef __MESH_BLUEPRINT_H__
#define __MESH_BLUEPRINT_H__
//
// The one Conduit Mesh Blueprint description of a rank's block, shared by
// every Conduit-based backend (#20). Ascent uses conduit::Node; Catalyst uses
// conduit_cpp::Node. describe() is a template so both build the same tree
// from the same code, which is what lets the backends be called equivalent.
//
// What it describes
//   * A uniform coordset and topology over the rank's full ghosted array:
//     (size + 2) points per axis, so (size + 1) cells per axis. Point i of
//     the local array sits at global index offset + i - 1; the origin is
//     (offset - 1) * spacing. The spacing is 0.1 per grid point, the value
//     every shipped Catalyst, Ascent and Kombyne camera assumes (the solver
//     itself is dimensionless with unit spacing).
//   * u and v as vertex fields, attached with set_external: the backend
//     reads the solver's own arrays, no copy. They stay valid between
//     steps because iterate() copies into them in place.
//   * Ghost fields (element association) from one ownership rule:
//     a cell belongs to the rank that owns its low corner point. Cells
//     whose low corner is in the low halo (local index 0 on any axis) are
//     ghosts, owned by the neighbour below. Cells whose low corner is the
//     last owned point bridge to the neighbour above and are owned here.
//     Every global cell, the periodic wrap-around cells included, is then
//     owned by exactly one rank.
//
// Ghost conventions (research and sources on #20)
//   * Ascent: element field "ascent_ghosts" (the default name; Ascent's
//     ghost_field_name option can change it). Before rendering, Ascent
//     keeps cells whose value is in [0, 0] and strips the rest
//     (ascent_main_runtime.cpp, vtkh_ghost_stripper with min 0, max 0).
//     So 0 = owned, 1 = ghost, stored as int32.
//   * VTK / ParaView: uint8 array "vtkGhostType" (vtkDataSetAttributes::
//     GhostArrayName()). A cell present on another rank is DUPLICATECELL
//     (1); a point present on another rank is DUPLICATEPOINT (1)
//     (vtkDataSetAttributes.h, CellGhostTypes and PointGhostTypes).
//     A Blueprint tree can hold only one field with that name, so the
//     element field is "vtkGhostType" and the point flags are offered as
//     "vtkGhostType_points" for the Catalyst adaptor to place (#21).
//   * Kombyne-lite: a char or int mask per cell, non-zero = real, 0 = ghost
//     (kombyne_data_ugrid.h); Ghosts::kombyne_cells. Kombyne takes its own
//     grid objects, not this tree, so its adaptor uses axis_points() and the
//     same ownership (#23).
//
// The halo must be current when a backend reads it: call
// GrayScott::refresh_halos() on output steps before describe().

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "gray-scott.h"

namespace gs_mesh
{

constexpr double kSpacing = 0.1;
constexpr std::int32_t kAscentOwned = 0;
constexpr std::int32_t kAscentGhost = 1;
constexpr std::uint8_t kVtkDuplicateCell = 1;  // vtkDataSetAttributes::DUPLICATECELL
constexpr std::uint8_t kVtkDuplicatePoint = 1; // vtkDataSetAttributes::DUPLICATEPOINT

// Coordinates of the local points along one axis: (offset - 1 + i) * spacing
// for i = 0 .. size + 1. For APIs that take explicit axis coordinates
// (Kombyne's rectilinear grid, #23); the same rule as the Blueprint origin.
inline std::vector<double> axis_points(std::size_t offset, std::size_t size)
{
    std::vector<double> x(size + 2);
    for (std::size_t i = 0; i < x.size(); i++)
        x[i] = (static_cast<double>(offset) - 1.0 + static_cast<double>(i)) * kSpacing;
    return x;
}

// Which ghost fields a backend reads. Each comes from the same ownership.
struct GhostFields
{
    bool ascent = false;     // "ascent_ghosts", element, int32
    bool vtk_cells = false;  // "vtkGhostType", element, uint8
    bool vtk_points = false; // "vtkGhostType_points", vertex, uint8
};

// Ghost flags for one rank's block. Built once; describe() attaches them
// with set_external, so they must outlive every publish that uses them.
struct Ghosts
{
    std::vector<std::int32_t> ascent_cells;
    std::vector<std::uint8_t> vtk_cells;
    std::vector<std::uint8_t> vtk_points;
    // Kombyne's mask is the reverse: non-zero = real, 0 = ghost
    // (kombyne_data_ugrid.h, kb_ugrid_set_ghost_cells).
    std::vector<unsigned char> kombyne_cells;
    std::size_t owned_cells = 0;
    std::size_t owned_points = 0;

    void build(const GrayScott &sim)
    {
        const std::size_t px = sim.size_x + 2, py = sim.size_y + 2, pz = sim.size_z + 2;
        const std::size_t cx = px - 1, cy = py - 1, cz = pz - 1;
        ascent_cells.assign(cx * cy * cz, kAscentOwned);
        vtk_cells.assign(cx * cy * cz, 0);
        owned_cells = 0;
        for (std::size_t k = 0; k < cz; k++)
            for (std::size_t j = 0; j < cy; j++)
                for (std::size_t i = 0; i < cx; i++)
                {
                    const std::size_t c = i + cx * (j + cy * k);
                    if (i == 0 || j == 0 || k == 0)
                    {
                        ascent_cells[c] = kAscentGhost;
                        vtk_cells[c] = kVtkDuplicateCell;
                    }
                    else
                        owned_cells++;
                }
        kombyne_cells.resize(vtk_cells.size());
        for (std::size_t c = 0; c < vtk_cells.size(); c++)
            kombyne_cells[c] = vtk_cells[c] ? 0 : 1;
        vtk_points.assign(px * py * pz, 0);
        owned_points = 0;
        for (std::size_t k = 0; k < pz; k++)
            for (std::size_t j = 0; j < py; j++)
                for (std::size_t i = 0; i < px; i++)
                {
                    const bool halo = i == 0 || j == 0 || k == 0 || i == px - 1 ||
                                      j == py - 1 || k == pz - 1;
                    if (halo)
                        vtk_points[i + px * (j + py * k)] = kVtkDuplicatePoint;
                    else
                        owned_points++;
                }
    }
};

// One field on the "mesh" topology, values attached without a copy. F is
// conduit::Node& (Ascent) or a conduit_cpp::Node handle (Catalyst, whose
// operator[] returns by value), hence the forwarding reference.
template <class F, class T>
void attach(F &&f, const char *association, T *values, std::size_t n)
{
    f["association"].set(std::string(association));
    f["topology"].set(std::string("mesh"));
    f["values"].set_external(values, n);
}

// Describe the rank's block into `mesh` (one Blueprint domain). Scalars are
// copied; u, v and the ghost flags are attached without copying.
template <class Node>
void describe(Node &mesh, const GrayScott &sim, const Ghosts &g, const GhostFields &which,
              int cycle, double time, int domain_id)
{
    const std::size_t px = sim.size_x + 2, py = sim.size_y + 2, pz = sim.size_z + 2;
    const std::size_t npts = px * py * pz;
    const std::size_t ncells = (px - 1) * (py - 1) * (pz - 1);

    mesh["state/cycle"].set(static_cast<std::int64_t>(cycle));
    mesh["state/time"].set(time);
    mesh["state/domain_id"].set(static_cast<std::int64_t>(domain_id));

    mesh["coordsets/coords/type"].set(std::string("uniform"));
    mesh["coordsets/coords/dims/i"].set(static_cast<std::int64_t>(px));
    mesh["coordsets/coords/dims/j"].set(static_cast<std::int64_t>(py));
    mesh["coordsets/coords/dims/k"].set(static_cast<std::int64_t>(pz));
    mesh["coordsets/coords/origin/x"].set((static_cast<double>(sim.offset_x) - 1.0) * kSpacing);
    mesh["coordsets/coords/origin/y"].set((static_cast<double>(sim.offset_y) - 1.0) * kSpacing);
    mesh["coordsets/coords/origin/z"].set((static_cast<double>(sim.offset_z) - 1.0) * kSpacing);
    mesh["coordsets/coords/spacing/dx"].set(kSpacing);
    mesh["coordsets/coords/spacing/dy"].set(kSpacing);
    mesh["coordsets/coords/spacing/dz"].set(kSpacing);

    mesh["topologies/mesh/type"].set(std::string("uniform"));
    mesh["topologies/mesh/coordset"].set(std::string("coords"));

    // The backends only read these arrays; conduit::Node takes non-const.
    attach(mesh["fields"]["u"], "vertex", const_cast<double *>(sim.u_ghost().data()), npts);
    attach(mesh["fields"]["v"], "vertex", const_cast<double *>(sim.v_ghost().data()), npts);
    if (which.ascent)
        attach(mesh["fields"]["ascent_ghosts"], "element",
               const_cast<std::int32_t *>(g.ascent_cells.data()), ncells);
    if (which.vtk_cells)
        attach(mesh["fields"]["vtkGhostType"], "element",
               const_cast<std::uint8_t *>(g.vtk_cells.data()), ncells);
    if (which.vtk_points)
        attach(mesh["fields"]["vtkGhostType_points"], "vertex",
               const_cast<std::uint8_t *>(g.vtk_points.data()), npts);
}

} // namespace gs_mesh

#endif

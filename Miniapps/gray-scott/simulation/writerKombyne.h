#ifndef __WRITERKOMBYNE_H__
#define __WRITERKOMBYNE_H__

#include "writer.h"
#include <vtkLogger.h>

// Include the C-style API headers for Kombyne Lite
#include <kombyne_execution.h>
#include <kombyne_data.h>
#include <kombyne_core_types.h>

class WriterKombyne : public Writer
{
public:
    WriterKombyne();
    ~WriterKombyne();

    void CreateWriter(const Settings &settings, const GrayScott &sim, int rank) override;
    void open(const std::string &fname, bool append, int rank) override;
    void write(int step, const GrayScott &sim, int rank, int numRanks) override;
    void close(int rank) override;
    void printSelf() override;

private:
    // Kombyne C-style handle for the pipeline collection
    kb_pipeline_collection_handle m_pipeline_collection = KB_HANDLE_NULL;
};

#endif // __WRITERKOMBYNE_H__

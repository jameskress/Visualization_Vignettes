import pandas as pd
import plotly.express as px
import glob
import argparse

def parse_and_process_kombyne_files():
    """
    Parses all 'timings.*.txt' files, aggregates the data by operation name,
    and prepares it for plotting.
    """
    timing_files = glob.glob("timings.*.txt")
    if not timing_files:
        print("Error: No 'timings.*.txt' files found in the current directory.")
        return None

    print(f"Found and processing {len(timing_files)} timing files...")
    all_data = []
    for filename in timing_files:
        with open(filename, 'r') as f:
            lines = f.readlines()
            # Skip header lines by looking for the start of the data
            data_lines = [line for line in lines if line.strip() and not line.strip().startswith('#') and not line.strip().startswith('TimerId')]
            for line in data_lines:
                try:
                    # Format is: TimerId, Level, Start, End, Time, Name
                    parts = line.strip().split(',')
                    time_val = float(parts[4])
                    # Name is the last part; strip whitespace
                    name = ','.join(parts[5:]).strip()
                    all_data.append([time_val, name])
                except (ValueError, IndexError):
                    continue # Skip malformed lines
    
    if not all_data:
        print("Error: No valid timing data was parsed.")
        return None

    # Create a DataFrame and aggregate the total time for each operation
    df = pd.DataFrame(all_data, columns=['Time', 'Name'])
    agg_df = df.groupby('Name')['Time'].sum().reset_index()

    # Create the structure for the sunburst plot
    # This creates a flat hierarchy with a single root node.
    total_time = agg_df['Time'].sum()
    plot_data = {
        "ids": ["Total"] + agg_df['Name'].tolist(),
        "parents": [""] + ["Total"] * len(agg_df),
        "values": [total_time] + agg_df['Time'].tolist(), # FIX: Added total_time to match other array lengths
        "names": ["Total"] + agg_df['Name'].tolist()
    }
    
    return plot_data

def plot_sunburst_to_pdf(data, output_filename="kombyne_sunburst_performance.pdf", show_plot=False):
    """
    Creates and saves a sunburst plot as a PDF file from the processed data.
    """
    if data is None:
        print("Cannot generate plot due to lack of processed data.")
        return

    print("Generating sunburst plot PDF...")
    
    fig = px.sunburst(
        data,
        ids='ids',
        parents='parents',
        values='values',
        names='names',
        branchvalues='total', # ensures leaves sum up to parent
        title='Kombyne Performance Breakdown (Time Summed Across All Ranks and Steps)'
    )

    fig.update_traces(
        textinfo='label+percent parent'
    )
    fig.update_layout(margin=dict(t=50, l=25, r=25, b=25))

    # Note: Exporting to PDF requires the 'kaleido' package.
    # You can install it using: pip install kaleido
    try:
        # Using write_image to save as a static PDF file
        fig.write_image(output_filename, width=1200, height=1200)
        print(f"Plot saved successfully to '{output_filename}'.")
    except ValueError as e:
        print(f"\n--- ERROR SAVING PDF ---")
        print(f"{e}")
        print("\nPlease ensure you have the 'kaleido' package installed.")
        print("Install it by running: pip install kaleido\n")

    if show_plot:
        fig.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse and visualize Kombyne timer files into a sunburst plot PDF.")
    parser.add_argument("--show", action="store_true", help="Display the plot interactively in a window after saving.")
    args = parser.parse_args()

    processed_data = parse_and_process_kombyne_files()
    plot_sunburst_to_pdf(processed_data, show_plot=args.show)


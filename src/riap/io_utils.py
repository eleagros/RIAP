def write_mp_fp_txt_format(
    mp_fp, 
    feature_matching_method: str = None
) -> str:
    """
    Formats matched feature points to tab-separated string format for saving.
    """
    # Define the header for the output file
    header = 'Index\txSource\tySource\txTarget\tyTarget\n'
    gen = enumerate(zip(mp_fp[1], mp_fp[0])) # automatic

    # Prepare the lines to be written to the file
    lines = [
        f"{index}\t{round(fp[0])}\t{round(fp[1])}\t{round(mp[0])}\t{round(mp[1])}\n"
        for index, (fp, mp) in gen
    ]
    
    return header + ''.join(lines)
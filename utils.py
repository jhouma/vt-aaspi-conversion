import time
import os, getpass
from datetime import datetime
import numpy as np
import os
import tkinter as tk
from tkinter import filedialog
from geoio import GeoIoVolume


class _Params:
    pass


def select_vt():

    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(master=root, title="Select VT File",
                                           filetypes=(("vt files", "*.vt"), ("all files", "*.*")))
    return file_path


def select_aaspi():

    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(master=root, title="Select AASPI File",
                                           filetypes=(("aaspi files", "*.H"), ("all files", "*.*")))
    return file_path


def select_output():

    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askdirectory(
        master=root, title="Select Output Path")
    return file_path


def set_vt_params(vt_vol):
    v = vt_vol
    p = _Params()

    p.vt_filename = vt_vol.get_filename()

    # get the header, survey and required transforms
    header, check = v.get_header_info()
    survey = v.get_survey()

    p.xform_ijk_tbt = survey.get_ijk_to_track_bin_time_transform()
    p.xform_ijk_xyz = survey.get_ijk_to_xyz_transform()
    p.volume_domain = _volume_domain(header.domain)

    # Calculate first, last, delta for each dimension for the aaspi header
    #
    # AASPI always wants data in ascending order
    # compute last track and switch first and last tracks if tracks are in
    # descending order.
    ntrk, dtrk, ftrk = check.num_tracks, check.delta_track, check.first_track
    ltrk = ftrk + dtrk * (ntrk - 1)
    if ftrk > ltrk:
        ftrk, ltrk = ltrk, ftrk
        dtrk = abs(dtrk)
    p.ftrk, p.dtrk, p.ltrk, p.ntrk = ftrk, dtrk, ltrk, ntrk

    # compute last bin and flag if bins are in descending order. Can't switch
    # bins as call to geoiovolume.get_float in IJK space expects the first
    # point to be less than or equal to the next point i.e. can't call
    # get_float( (0,100,0) , (0,0,0) )
    nbin, dbin, fbin = check.num_bins, check.delta_bin, check.first_bin
    lbin = fbin + dbin * (nbin - 1)
    if fbin > lbin:
        negbin = True
        dbin = abs(dbin)
    else:
        negbin = False
    p.fbin, p.dbin, p.lbin, p.nbin, p.negbin = fbin, dbin, lbin, nbin, negbin

    # Compute last sample
    p.nsmp, p.dsmp, p.fsmp = check.num_samples, check.digi, check.zero_time
    p.lsmp = p.fsmp + p.dsmp * (p.nsmp - 1)

    return p


def set_aaspi_params(vt_filename, output_dir, horizontal_units, vertical_units):
    p = _Params()

    p.vt_filename = vt_filename
    p.output_dir = output_dir

    vt_name = os.path.basename(p.vt_filename)

    # use AASPI naming convention
    # Header file .H points to the binary data in H@
    # the idents for each trace are stored separate idents_binary file
    # H@@@ which has H@@ as the the header
    # these are intermediate volumes before pad3d
    p.nopad_header_name = vt_name + '_nopad.H'
    p.nopad_binary_name = p.nopad_header_name + '@'
    p.nopad_idents_header_name = p.nopad_header_name + '@@'
    p.nopad_idents_binary_name = p.nopad_header_name + '@@@'

    # these will be the final names after pad3d
    p.header_name = vt_name + '.H'
    p.binary_name = p.header_name + '@'
    p.idents_header_name = p.header_name + '@@'
    p.idents_binary_name = p.header_name + '@@@'

    # uniq_proj can be anything. using VT name as convience
    p.uniq_proj = vt_name

    p.horizontal_units = horizontal_units
    p.vertical_units = vertical_units

    # determined by trial and error that the below 11 idents are required to
    # run AAPSI pad3d program
    p.idents = {"cdp_no": 0, "line_no": 1, "muts": 2, "mute": 3, "trid": 4,
                "laga": 5, "scalco": 6, "ns": 7, "dt": 8, "cdp_y": 9,
                "cdp_x": 10}

    return p


def _volume_domain(domain_):
    domain = {0: "Time", 1: "Seismic Depth", 2: "Depth", 4: "Unknown"}
    return domain.get(domain_, "Invalid domain")


def write_aaspi_header(vp_params, ap_params):
    vp = vp_params
    ap = ap_params

    localtime = time.asctime(time.localtime(time.time()))
    hostname = os.uname().nodename

    # Set the values for the aaspi header
    # fastest axis - always vertical time or depth
    n1, d1, o1 = vp.nsmp, vp.dsmp, vp.fsmp
    l1 = vp.volume_domain
    u1 = ap.vertical_units

    # middle axis - always bin - map to cdp
    n2, d2, o2 = vp.nbin, vp.dbin, vp.fbin
    if vp.negbin:
        o2 = vp.lbin
    l2 = "Bin"

    # slowest axis - always trk - map to line_no
    n3, d3, o3 = vp.ntrk, vp.dtrk, vp.ftrk
    l3 = "Track"

    # Write the aaspi header. Use xdr_float big endian format for the aaspi
    # data, this requires a byteswap when writing data from a litte endian
    # architecture such as x86 Linux and Windows.
    aaspi_header = f'vt_to_aaspi.py:  {localtime} host:{hostname}\n\n'
    aaspi_header += f'input_vt_filename={vp.vt_filename}\n'
    aaspi_header += f'in="{ap.nopad_binary_name}"\n'
    aaspi_header += f'hff="{ap.nopad_idents_header_name}"\n'
    aaspi_header += 'esize=4\n'
    aaspi_header += 'data_format="xdr_float"\n'
    aaspi_header += f'n1={n1} n2={n2} n3={n3}\n'
    aaspi_header += f'd1={d1} d2={d2} d3={d3}\n'
    aaspi_header += f'o1={o1} o2={o2} o3={o3}\n'
    aaspi_header += f'label1={l1}\n'
    aaspi_header += f'label2={l2}\n'
    aaspi_header += f'label3={l3}\n'
    aaspi_header += f'unit1={u1}\n'

    # print(aaspi_header)
    with open(os.path.join(ap.output_dir, ap.nopad_header_name), 'w') as f:
        f.write(aaspi_header)
        f.close()


def write_aaspi_idents_header(vp_params, ap_params):
    vp = vp_params
    ap = ap_params

    localtime = time.asctime(time.localtime(time.time()))
    hostname = os.uname().nodename

    # write header file for the idents
    n1, d1, o1 = len(ap.idents), 1, 1
    n2, d2, o2 = vp.nbin, 1, 1
    n3, d3, o3 = vp.ntrk, 1, 1

    aaspi_header = f'vt_to_aaspi.py: {localtime} host:{hostname}\n\n'
    aaspi_header += f'input_vt_filename={vp.vt_filename}\n'
    aaspi_header += f'in="{ap.nopad_idents_binary_name}"\n'
    aaspi_header += 'esize=4\n'
    aaspi_header += 'data_format="xdr_float"\n'
    aaspi_header += f'n1={n1} n2={n2} n3={n3}\n'
    aaspi_header += f'd1={d1} d2={d2} d3={d3}\n'
    aaspi_header += f'o1={o1} o2={o2} o3={o3}\n'
    for i, j in ap.idents.items():
        aaspi_header += f'hdrkey{j + 1}="{i}" hdrtype{j + 1}="scalar_int" '
        aaspi_header += f'hdrfmt{j + 1}="xdr_int"\n'

    # print(aaspi_header)
    with open(os.path.join(ap.output_dir,
                           ap.nopad_idents_header_name), 'w') as f:
        f.write(aaspi_header)
        f.close()


def write_aaspi_binaries_from_vt(vt_vol, vt_params, aaspi_params, progress, status_text):
    ap = aaspi_params
    vp = vt_params
    v = vt_vol
    xform_ijk_tbt = vp.xform_ijk_tbt
    xform_ijk_xyz = vp.xform_ijk_xyz

    # Write traces and idents together in same routine to prevent getting them
    # out of sync
    # open binary files for the data and idents
    fb = open(os.path.join(ap.output_dir,
                           ap.nopad_binary_name), 'wb')
    fib = open(os.path.join(ap.output_dir,
                            ap.nopad_idents_binary_name), 'wb')

    idents = ap.idents
    # array to hold the idents - need 4 byte integer
    hdr_idents = np.zeros((vp.nbin, len(idents)), dtype='i4')

    # set the idents which are the same for every trace
    hdr_idents[:, idents.get("muts")] = 0
    hdr_idents[:, idents.get("mute")] = 0
    hdr_idents[:, idents.get("trid")] = 1
    hdr_idents[:, idents.get("laga")] = 0
    hdr_idents[:, idents.get("scaleco")] = 1
    hdr_idents[:, idents.get("ns")] = vp.nsmp
    hdr_idents[:, idents.get("dt")] = vp.dsmp

    # Always write out samples, bins, then tracks regardless of input data sort
    # Always write out bins and tracks in positive direction regardless of
    # input data sort
    num = 0
    print(f'Writing tracks: {vp.ftrk} to {vp.ltrk} delta {vp.dtrk}')
    if vp.negbin:
        print(f'Flipping bins : {vp.lbin} to {vp.fbin} delta {vp.dbin}')

    for trk in range(vp.ftrk, vp.ltrk + vp.dtrk, vp.dtrk):
        # print progress messages - print track number every 100 tracks
        # .'s for the other tracks. print all on same line
        progress.progress((trk-vp.ftrk)/(vp.ltrk+vp.dtrk-vp.ftrk))

        num += 1

        status_text.text('Conversion Progress : %d/%d' %
                         (num, abs(vp.ltrk-vp.ftrk)/vp.dtrk+1))

        #
        beg = (trk, vp.fbin, vp.fsmp)
        end = (trk, vp.lbin, vp.lsmp)
        bijk = xform_ijk_tbt.from_target(beg)
        eijk = xform_ijk_tbt.from_target(end)

        # write one track at a time in big endian order
        dataslice = np.array(v.get_float(bijk, eijk), dtype=np.float32)
        if vp.negbin:
            np.flip(dataslice, axis=0).byteswap().tofile(fb)
        else:
            dataslice.byteswap().tofile(fb)

        # now the idents - make sure the idents match the track just written
        start_i, end_i = int(bijk[0]), int(eijk[0]) + 1
        start_j, end_j = int(bijk[1]), int(eijk[1]) + 1
        # xyz, and tbt should always be a 2D array because one of i or j is the
        # track direction and start - end will be 1
        xyz = np.array([xform_ijk_xyz.to_target((i, j, 0))
                        for i in range(start_i, end_i)
                        for j in range(start_j, end_j)])
        tbt = np.array([xform_ijk_tbt.to_target((i, j, 0))
                        for i in range(start_i, end_i)
                        for j in range(start_j, end_j)])

        # track is always line_no, bin is always cdp_no
        # map x and y to cdp_x and cdp_y
        hdr_idents[:, idents.get("line_no")] = tbt[:, 0]
        hdr_idents[:, idents.get("cdp_no")] = tbt[:, 1]
        hdr_idents[:, idents.get("cdp_x")] = xyz[:, 0]
        hdr_idents[:, idents.get("cdp_y")] = xyz[:, 1]
        # write the idents for this track in big endian order
        if vp.negbin:
            np.flip(hdr_idents, axis=0).byteswap().tofile(fib)

        else:
            hdr_idents.byteswap().tofile(fib)

    # print new line after progress messages
    print('')

    # close the binary files
    fb.close()
    fib.close()


def write_vt_data(session_state, progress, status_text):

    inputvt = GeoIoVolume(session_state.inputvt)
    header, check = inputvt.get_header_info()
    survey = inputvt.get_survey()

    hdr = {}
    with open(session_state.inputaaspi) as f:
        for line in f:
            arr = line.split()
            for item in arr:
                if "=" in item:
                    hdr[item.split('=')[0].replace('"', '').replace("'", "")] = item.split('=')[
                        1].replace('"', '').replace("'", "")

    hdr['hff'] = os.path.join('/'.join(session_state.inputaaspi.split('/')[:-1]), hdr['hff'])
    hdr['in'] = os.path.join('/'.join(session_state.inputaaspi.split('/')[:-1]), hdr['in'])

    hff = {}
    with open(hdr['hff']) as f:
        for line in f:
            arr = line.split()
            for item in arr:
                if "=" in item:
                    hff[item.split('=')[0].replace('"', '').replace("'", "")] = item.split('=')[
                        1].replace('"', '').replace("'", "")

    hff['in'] = os.path.join(
        '/'.join(session_state.inputaaspi.split('/')[:-1]), hff['in'])

    header.min_clip_amp = float(hdr['min_amplitude'])
    header.max_clip_amp = float(hdr['max_amplitude'])

    outputvt_name = os.path.join(
        session_state.outputpath, session_state.inputaaspi.split('/')[-1].replace(".H", "_aaspi.vt"))

    try:
        os.remove(outputvt_name)
        os.remove(outputvt_name+'.slm')
    except:
        pass

    outputvt = GeoIoVolume(outputvt_name, header, check, survey)

    xform_ijk_tbt = survey.get_ijk_to_track_bin_time_transform()

    hffdata = np.fromfile(hff['in'], dtype='>i4').reshape(
        int(hdr['n3']), int(hdr['n2']), int(hff['n1']))

    for ii in range(int(hdr['n3'])):
        progress.progress(ii/int(hdr['n3']))
        status_text.text('Conversion Progress : %d/%d' %
                         (ii+1, int(hdr['n3'])))
        for jj in range(int(hdr['n2'])):
            trk, bin = hffdata[ii, jj, 1], hffdata[ii, jj, 0]
            i, j, _ = xform_ijk_tbt.from_target((trk, bin, 0))
            trace = np.fromfile(hdr['in'], dtype='>f4', count=int(
                hdr['n1']), offset=int(hdr['n1'])*(jj+int(hdr['n2'])*ii)*4)
            outputvt.put(trace.astype(np.float32), int(i), int(j))


def run_pad3d(aaspi_params):
    # Assumes AASPIHOME env variable is set correctly
    # Make a list of argument needed by pad3d
    p = aaspi_params
    pad3d_script = 'LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:${AASPIHOME}/lib64:${AASPIHOME}/ext_lib64/intel64 \n'
    pad3d_script += '${AASPIHOME}/bin64/pad3d '
    pad3d_script += f'unique_project_name="{p.uniq_proj}" \\\n'
    pad3d_script += f'unpadded_fn="{p.nopad_header_name}" \\\n'
    pad3d_script += f'padded_fn="{p.header_name}" \\\n'
    pad3d_script += f'horizontal_units="{p.horizontal_units}" \\\n'
    pad3d_script += f'vertical_units="{p.vertical_units}" \n\n'
    pad3d_script += 'if [ "$?" -ne 0 ]; then \n'
    pad3d_script += '   echo "" \n'
    pad3d_script += '   echo "" \n'
    pad3d_script += '   echo "ERROR: pad3d did not complete successfully" \n'
    pad3d_script += '   echo "       see errors in" `pwd` \n'
    pad3d_script += '   echo "" \n'
    pad3d_script += 'else\n'
    pad3d_script += f'   rm {p.nopad_header_name}\n'
    pad3d_script += f'   rm {p.nopad_binary_name}\n'
    pad3d_script += f'   rm {p.nopad_idents_header_name}\n'
    pad3d_script += f'   rm {p.nopad_idents_binary_name}\n'
    pad3d_script += 'fi\n'

    #    print(pad3d_script)
    pad_file = os.path.join(p.output_dir, 'pad3d.sh')
    with open(pad_file, 'w') as f:
        f.write(pad3d_script)
        f.close()
    os.chmod(pad_file, 0o755)
    curr_dir = os.getcwd()
    os.chdir(p.output_dir)
    os.system("./pad3d.sh")
    os.chdir(curr_dir)

def track_usage(msg, email_address='jie.hou@shell.com'):
    """ Track the usage for this application.
    
    Parameters
    ----------
    email_address: str
        The email address will receive the information about the usage.
    msg: dict
        A dictionary including all the messages will be included in the email.
        
    Returns
    -------
    """
    
    current_username = getpass.getuser()
    email_subject = '"VT-AASPI Converter"'
    body_text = '"User Name: '+current_username + '\n'
    body_text+= 'Run Time:' + datetime.today().strftime('%Y-%m-%d') +'\n'
    for key, value in msg.items():
        body_text += key + ': '+value +'\n'
        
    body_text += '"'
    
    try:
        os.system('echo {} | mail -s {} {}'.format(body_text, email_subject, email_address))
    except:
        pass 

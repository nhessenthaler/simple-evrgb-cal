def calibration_s_pattern():

    # --- INITIALIZATION ---    
    # Base Orientation 
    # Start orientation (pointing straight at screen, has to be tuned for each scene)
    base_rx = {base_rx}
    base_ry = {base_ry}
    base_rz = {base_rz}

    # Start position (has to be moved to manually, read out then put to the parameter sheet)
    base_x = {base_x}
    base_y = {base_y}
    base_z = {base_z}

    # Midpoint positions
    midpoint_x = {midpoint_x}
    midpoint_z = {midpoint_z}

    # Additional positions
    extra_pos1_z = {extra_pos1_z}
    extra_pos1_ry = {extra_pos1_ry}
    extra_pos2_z = {extra_pos2_z}
    extra_pos2_ry = {extra_pos2_ry}
    extra_pos3_x = {extra_pos3_x}
    extra_pos3_rz = {extra_pos3_rz}
    extra_pos4_x = {extra_pos4_x}
    extra_pos4_rz = {extra_pos4_rz}

    # Set wait signal for for the main python application
    set_standard_digital_out(1, True)

    # Reset signals to ensure clean state on every script start (including restarts after abort)
    set_standard_digital_out(2, False)

    # Move the robot arm to the start position
    movel(p[base_x, base_y, base_z, base_rx, base_ry, base_rz], t={t_move_start})

    # --- SNAKE MOVEMENT ---
    row_iterator = 0
    while row_iterator < {calibration_rows}:

        # Calculate vertical position and check whether row is odd or even
        current_z = base_z - (row_iterator * {step_z})
        is_even = (row_iterator / 2.0 == floor(row_iterator / 2.0))
        
        column_iterator = 0
        while column_iterator < {calibration_columns}:

            # Robot arm is moving to the left
            if (is_even):
                current_column = column_iterator
            
            # Robot arm is moving to the right
            else:
                current_column = ({calibration_columns} - 1) - column_iterator
            end
            
            # Horizontal Position
            curr_x = base_x + (current_column * {step_x})
            
            # Target pose determination
            target_pose = p[curr_x, base_y, current_z, base_rx, base_ry, base_rz]
            
            # Signal moving, wait, move to target pose, wait, then signal position reached
            sleep({t_wait})
            set_standard_digital_out(2, False)
            movel(target_pose, t={t_move})
            set_standard_digital_out(2, True)
            sleep({t_wait})
            
            
            # Increment the colum within the row
            column_iterator = column_iterator + 1
        end

        # Increment the row
        row_iterator = row_iterator + 1
    end

    # --- DEPTH ZOOM ---
    sleep({t_wait})
    set_standard_digital_out(2, False)
    movel(p[midpoint_x, base_y + ({min_depth_position} * {step_y}), midpoint_z, base_rx, base_ry, base_rz], t={t_move_start_depth})

    depth_iterator = {min_depth_position}
    while depth_iterator <= {max_depth_position}:

        # Calculate depth position
        current_depth = base_y + (depth_iterator * {step_y})
        textmsg(depth_iterator)

        # Target pose determination
        target_pose = p[midpoint_x, current_depth, midpoint_z, base_rx, base_ry, base_rz]

        # Signal moving, wait, move to target pose, wait, then signal position reached
        sleep({t_wait})
        set_standard_digital_out(2, False)
        movel(target_pose, t={t_move})
        set_standard_digital_out(2, True)
        sleep({t_wait})

        depth_iterator = depth_iterator + 1
    end

    # --- YAW ---
    yaw_iterator = {min_rotation_position}

    # Base pose (used for yaw transformations)
    base_pose = p[midpoint_x, base_y, midpoint_z, base_rx, base_ry, base_rz]

    while yaw_iterator <= {max_rotation_position}:

        # Calculate yaw position
        yaw_pose = pose_trans(base_pose, p[0, 0, 0, 0, yaw_iterator * {step_ry}, 0])

        # Signal moving, wait, move to target pose, wait, then signal position reached
        sleep({t_wait})
        set_standard_digital_out(2, False)
        movel(yaw_pose, t={t_move})
        set_standard_digital_out(2, True)
        sleep({t_wait})
        
        yaw_iterator = yaw_iterator + 1
    end

    # --- ADDITIONAL POSITIONS ---
    # Sweep: Position 1 -> Position 2 (z and ry vary)
    sweep_iter = 0
    while sweep_iter <= {sweep_steps}:
        sweep_frac = (sweep_iter * 1.0) / {sweep_steps}
        sweep_z = extra_pos1_z + sweep_frac * (extra_pos2_z - extra_pos1_z)
        sweep_ry = extra_pos1_ry + sweep_frac * (extra_pos2_ry - extra_pos1_ry)
        sleep({t_wait})
        set_standard_digital_out(2, False)
        movel(p[base_x, base_y, sweep_z, base_rx, sweep_ry, base_rz], t={t_move_start})
        set_standard_digital_out(2, True)
        sleep({t_wait})
        sweep_iter = sweep_iter + 1
    end

    # Sweep: Position 3 -> Position 4 (x and rz vary)
    sweep_iter = 0
    while sweep_iter <= {sweep_steps}:
        sweep_frac = (sweep_iter * 1.0) / {sweep_steps}
        sweep_x = extra_pos3_x + sweep_frac * (extra_pos4_x - extra_pos3_x)
        sweep_rz = extra_pos3_rz + sweep_frac * (extra_pos4_rz - extra_pos3_rz)
        sleep({t_wait})
        set_standard_digital_out(2, False)
        movel(p[sweep_x, base_y, base_z, base_rx, base_ry, sweep_rz], t={t_move_start})
        set_standard_digital_out(2, True)
        sleep({t_wait})
        sweep_iter = sweep_iter + 1
    end

    # Sweep: Diagonal 1 -> P1 to P2 (x, z, rx, ry, rz vary)
    # Normalize angular deltas to shortest path [-pi, pi]
    d1_delta_rx = {diag_pos2_rx} - {diag_pos1_rx}
    if (d1_delta_rx > 3.14159):
        d1_delta_rx = d1_delta_rx - 6.28318
    end
    if (d1_delta_rx < -3.14159):
        d1_delta_rx = d1_delta_rx + 6.28318
    end
    d1_delta_ry = {diag_pos2_ry} - {diag_pos1_ry}
    if (d1_delta_ry > 3.14159):
        d1_delta_ry = d1_delta_ry - 6.28318
    end
    if (d1_delta_ry < -3.14159):
        d1_delta_ry = d1_delta_ry + 6.28318
    end
    d1_delta_rz = {diag_pos2_rz} - {diag_pos1_rz}
    if (d1_delta_rz > 3.14159):
        d1_delta_rz = d1_delta_rz - 6.28318
    end
    if (d1_delta_rz < -3.14159):
        d1_delta_rz = d1_delta_rz + 6.28318
    end
    sweep_iter = 0
    while sweep_iter <= {sweep_steps}:
        sweep_frac = (sweep_iter * 1.0) / {sweep_steps}
        sweep_x = {diag_pos1_x} + sweep_frac * ({diag_pos2_x} - {diag_pos1_x})
        sweep_z = {diag_pos1_z} + sweep_frac * ({diag_pos2_z} - {diag_pos1_z})
        sweep_rx = {diag_pos1_rx} + sweep_frac * d1_delta_rx
        sweep_ry = {diag_pos1_ry} + sweep_frac * d1_delta_ry
        sweep_rz = {diag_pos1_rz} + sweep_frac * d1_delta_rz
        sleep({t_wait})
        set_standard_digital_out(2, False)
        movel(p[sweep_x, base_y, sweep_z, sweep_rx, sweep_ry, sweep_rz], t={t_move_start})
        set_standard_digital_out(2, True)
        sleep({t_wait})
        sweep_iter = sweep_iter + 1
    end

    # Sweep: Diagonal 2 -> P3 to P4 (x, z, rx, ry, rz vary)
    # Normalize angular deltas to shortest path [-pi, pi]
    d2_delta_rx = {diag_pos4_rx} - {diag_pos3_rx}
    if (d2_delta_rx > 3.14159):
        d2_delta_rx = d2_delta_rx - 6.28318
    end
    if (d2_delta_rx < -3.14159):
        d2_delta_rx = d2_delta_rx + 6.28318
    end
    d2_delta_ry = {diag_pos4_ry} - {diag_pos3_ry}
    if (d2_delta_ry > 3.14159):
        d2_delta_ry = d2_delta_ry - 6.28318
    end
    if (d2_delta_ry < -3.14159):
        d2_delta_ry = d2_delta_ry + 6.28318
    end
    d2_delta_rz = {diag_pos4_rz} - {diag_pos3_rz}
    if (d2_delta_rz > 3.14159):
        d2_delta_rz = d2_delta_rz - 6.28318
    end
    if (d2_delta_rz < -3.14159):
        d2_delta_rz = d2_delta_rz + 6.28318
    end
    sweep_iter = 0
    while sweep_iter <= {sweep_steps}:
        sweep_frac = (sweep_iter * 1.0) / {sweep_steps}
        sweep_x = {diag_pos3_x} + sweep_frac * ({diag_pos4_x} - {diag_pos3_x})
        sweep_z = {diag_pos3_z} + sweep_frac * ({diag_pos4_z} - {diag_pos3_z})
        sweep_rx = {diag_pos3_rx} + sweep_frac * d2_delta_rx
        sweep_ry = {diag_pos3_ry} + sweep_frac * d2_delta_ry
        sweep_rz = {diag_pos3_rz} + sweep_frac * d2_delta_rz
        sleep({t_wait})
        set_standard_digital_out(2, False)
        movel(p[sweep_x, base_y, sweep_z, sweep_rx, sweep_ry, sweep_rz], t={t_move_start})
        set_standard_digital_out(2, True)
        sleep({t_wait})
        sweep_iter = sweep_iter + 1
    end

    # Move the robot arm back to the start position
    set_standard_digital_out(2, False)
    sleep({t_wait})
    movel(p[base_x, base_y, base_z, base_rx, base_ry, base_rz], t={t_move_start})
    sleep({t_wait})
    
    # Signal for main Python script for 
    set_standard_digital_out(1, False)
    
end


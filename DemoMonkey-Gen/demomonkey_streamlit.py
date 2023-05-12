import streamlit as st
from generate_demomonkey import main

# Title
st.sidebar.title("DemoMonkey Config Generator")

# Input fields
realm = st.sidebar.text_input("O11y Realm", "us0")
token = st.sidebar.text_input("O11y Token", "", type="password")
environment = st.sidebar.text_input("Demo Environment", "")
base_domain = st.sidebar.text_input("Base Domain (optional)", "")

# Run button
if st.sidebar.button("Generate"):
    # placeholder for the "please wait" message
    placeholder = st.empty()
    placeholder.text("Please wait...")

    try:
        # Call the main function and capture the output
        demomonkey_config_file = main(realm, token, environment, base_domain)

        # Clear the "please wait" message
        placeholder.empty()
        
        # Check if demomonkey_config_file is None or not
        if demomonkey_config_file is not None:
            # Read the contents of the 'demomonkey_config.mnky' file
            with open(demomonkey_config_file, 'r') as file:
                demomonkey_config = file.read()
                
            # Display the output
            st.text(demomonkey_config)
        else:
            st.error("The function did not return a file name.")
    except Exception as e:
        # Display the error message
        st.error(f"An error occurred: {e}")

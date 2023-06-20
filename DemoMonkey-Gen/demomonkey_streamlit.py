import streamlit as st
from generate_demomonkey import main
import os

# Title
st.sidebar.title("DemoMonkey Config Generator")

# Dropdown menu for templates
templates_dir = 'templates'
templates = [os.path.splitext(template)[0] for template in os.listdir(templates_dir)]
selected_template = st.sidebar.selectbox("Select a template (optional)", ['None'] + templates)

if selected_template and selected_template != "None":
    # If a template is selected, read and display it
    with open(os.path.join(templates_dir, selected_template + ".mnky"), 'r') as file:
        template_content = file.read()

    st.text(template_content)
else:
    # Input fields
    realm = st.sidebar.text_input("O11y Realm", "us1")
    token = st.sidebar.text_input("O11y Token", "", type="password")
    environment = st.sidebar.text_input("Demo Environment (RUM)", "")
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

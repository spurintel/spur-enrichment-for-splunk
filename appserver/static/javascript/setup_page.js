"use strict";

const appName = "spur-enrichment-for-splunk";
const appNamespace = {
    owner: "nobody",
    app: appName,
    sharing: "app",
};
const pwRealm = "spur_splunk_realm";
const pwName = "token";

// Splunk Web Framework Provided files
require([
    "jquery", "splunkjs/splunk",
], function($, splunkjs) {
    console.log("setup_page.js require(...) called");

    // Track which configurations are available
    let configAvailability = {
        threshold: false,
        apiUrl: false
    };

    // Check configuration availability when page loads
    checkConfigurationAvailability();

    // Register .on( "click", handler ) for "Complete Setup" button
    $("#setup_button").click(completeSetup);

    // onclick function for "Complete Setup" button from setup_page_dashboard.xml
    async function completeSetup() {
        console.log("setup_page.js completeSetup called");
        // Value of password_input from setup_page_dashboard.xml
        const passwordToSave = $('#password_input').val();
        const thresholdToSave = $('#threshold_input').val();
        const apiUrlToSave = $('#api_url_input').val();
        let stage = 'Initializing the Splunk SDK for Javascript';
        
        const warnings = [];
        
        try {
            // Initialize a Splunk Javascript SDK Service instance
            const http = new splunkjs.SplunkWebHttp();
            const service = new splunkjs.Service(
                http,
                appNamespace,
            );
            // Get app.conf configuration
            stage = 'Retrieving configurations SDK collection';
            const configCollection = service.configurations(appNamespace);
            await configCollection.fetch();
            stage = `Retrieving app.conf values for ${appName}`;
            const appConfig = configCollection.item('app');
            await appConfig.fetch();
            stage = `Retrieving app.conf [install] stanza values for ${appName}`;
            const installStanza = appConfig.item('install');
            await installStanza.fetch();
            // Verify that app is not already configured
            const isConfigured = installStanza.properties().is_configured;
            if (isTrue(isConfigured)) {
                console.warn(`App is configured already (is_configured=${isConfigured}), skipping setup page...`);
                reloadApp(service);
                redirectToApp();
                return;
            }

            // Setup configurations that we know are available
            if (configAvailability.threshold) {
                await attemptThresholdConfig(configCollection, thresholdToSave, warnings);
            }

            if (configAvailability.apiUrl) {
                await attemptApiUrlConfig(configCollection, apiUrlToSave, warnings);
            }

            // Critical: Save the password/token
            await savePasswordToken(service, passwordToSave, installStanza, warnings);

        } catch (e) {
            console.error(e);
            $('.error').show();
            $('#error_details').show();
            let errText = `Critical error encountered during stage: ${stage}<br>`;
            errText += (e.toString() === '[object Object]') ? '' : e.toString();
            if (e.hasOwnProperty('status')) errText += `<br>[${e.status}] `;
            if (e.hasOwnProperty('responseText')) errText += e.responseText;
            $('#error_details').html(errText);
        }
    }

    // Configure threshold setting (we know it's available)
    async function attemptThresholdConfig(configCollection, thresholdToSave, warnings) {
        console.log("Setting threshold configuration...");
        const threshold = parseInt(thresholdToSave) || 0;
        if (threshold < 0) {
            throw new Error('Threshold value must be non-negative');
        }
        
        const alertCollection = configCollection.item('customalerts');
        await alertCollection.fetch();
        const alertStanza = alertCollection.item('alerts');
        await alertStanza.fetch();
        await alertStanza.update({
            low_query_threshold: threshold
        });
        console.log(`Successfully set threshold to ${threshold}`);
    }

    // Configure API URL setting (we know it's available)
    async function attemptApiUrlConfig(configCollection, apiUrlToSave, warnings) {
        console.log("Setting API URL configuration...");
        const apiCollection = configCollection.item('api');
        await apiCollection.fetch();
        const apiStanza = apiCollection.item('api');
        await apiStanza.fetch();
        await apiStanza.update({
            context_api_url: apiUrlToSave || 'https://api.spur.us/v2/context/'
        });
        console.log(`Successfully set API URL to ${apiUrlToSave || 'default'}`);
    }

    // Save password/token (critical operation)
    async function savePasswordToken(service, passwordToSave, installStanza, warnings) {
        const passKey = `${pwRealm}:${pwName}:`;
        const passwords = service.storagePasswords(appNamespace);
        await passwords.fetch();
        const existingPw = passwords.item(passKey);

        function passwordCallback(err, resp) {
            if (err) {
                console.error("Password save failed:", err);
                throw err;
            }
            
            // Setup completed successfully
            setIsConfigured(installStanza, 1);
            reloadApp(service);
            
            // Show success message with any warnings
            if (warnings.length > 0) {
                showWarnings(warnings);
            }
            $('.success').show();
            redirectToApp();
        }

        if (!existingPw) {
            // Secret doesn't exist, create new one
            console.log(`Creating new password for realm = ${pwRealm}`);
            passwords.create({
                name: pwName,
                password: passwordToSave,
                realm: pwRealm,
            }, passwordCallback);
        } else {
            // Secret exists, update to new value
            console.log(`Updating existing password for realm = ${pwRealm}`);
            existingPw.update({
                password: passwordToSave,
            }, passwordCallback);
        }
    }

    // Show warnings for non-critical configuration failures
    function showWarnings(warnings) {
        if (warnings.length > 0) {
            $('#warnings').show();
            $('#warning_details').html(warnings.map(w => `• ${w}`).join('<br>'));
        }
    }

    // Check which configurations are available when page loads
    async function checkConfigurationAvailability() {
        console.log("Checking configuration availability...");
        const warnings = [];
        
        try {
            // Initialize Splunk SDK
            const http = new splunkjs.SplunkWebHttp();
            const service = new splunkjs.Service(http, appNamespace);
            const configCollection = service.configurations(appNamespace);
            await configCollection.fetch();

            // Check if customalerts.conf is available
            try {
                const alertCollection = configCollection.item('customalerts');
                await alertCollection.fetch();
                const alertStanza = alertCollection.item('alerts');
                await alertStanza.fetch();
                configAvailability.threshold = true;
                console.log("Threshold configuration is available");
            } catch (e) {
                console.warn("Threshold configuration not available:", e);
                warnings.push("Query threshold warnings are not available in this environment");
                configAvailability.threshold = false;
            }

            // Check if api.conf is available
            try {
                const apiCollection = configCollection.item('api');
                await apiCollection.fetch();
                const apiStanza = apiCollection.item('api');
                await apiStanza.fetch();
                configAvailability.apiUrl = true;
                console.log("API URL configuration is available");
            } catch (e) {
                console.warn("API URL configuration not available:", e);
                warnings.push("Custom API URL configuration is not available in this environment");
                configAvailability.apiUrl = false;
            }

        } catch (e) {
            console.error("Failed to check configuration availability:", e);
            warnings.push("Unable to check configuration availability");
        }

        // Show the configuration form with only available options
        showConfigurationForm(warnings);
    }

    // Show the configuration form with only available inputs
    function showConfigurationForm(warnings) {
        // Hide loading indicator
        $('#loading_indicator').hide();
        
        // Show available configuration inputs
        if (configAvailability.threshold) {
            $('.threshold-config').show();
        }
        if (configAvailability.apiUrl) {
            $('.api-url-config').show();
        }
        
        // Show any warnings about unavailable configurations
        if (warnings.length > 0) {
            showWarnings(warnings);
        }
        
        // Show the main configuration form
        $('#config_form').show();
        
        console.log("Configuration form displayed with available options");
    }

    async function setIsConfigured(installStanza, val) {
        await installStanza.update({
            is_configured: val
        });
    }

    async function reloadApp(service) {
        // In order for the app to register that it has been configured
        // it first needs to be reloaded
        var apps = service.apps();
        await apps.fetch();

        var app = apps.item(appName);
        await app.fetch();
        await app.reload();
    }

    function redirectToApp(waitMs) {
        setTimeout(() => {
            window.location.href = `/app/${appName}`;
        }, 800); // wait 800ms and redirect
    }

    function isTrue(v) {
        if (typeof(v) === typeof(true)) return v;
        if (typeof(v) === typeof(1)) return v!==0;
        if (typeof(v) === typeof('true')) {
            if (v.toLowerCase() === 'true') return true;
            if (v === 't') return true;
            if (v === '1') return true;
        }
        return false;
    }
});
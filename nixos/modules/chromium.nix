{ ... }:

{
  programs.chromium = {
    enable = true;
    # extensions = [
    #   "cjpalhdlnbpafiamejdnhcphjbkeiagm" # ublock origin
    #   "fnaicdffflnofjppbagibeoednhnbjhg" # floccus-bookmarks-sync
    #   "nngceckbapebfimnlniiiahkandclblb" # Bitwarden
    #   "jinjaccalgkegednnccohejagnlnfdag" # violentmonkey
    #   "bdiifdefkgmcblbcghdlonllpjhhjgof" # kiss-translator
    #   "djflhoibgkdhkhhcedjiklpkjnoahfmg" # user-agent-switcher
    #   "mpiodijhokgodhhofbcjdecpffjipkle" # singlefile
    #   "jpbjcnkcffbooppibceonlgknpkniiff" # global-speed
    #   "gbkeegbaiigmenfmjfclcdgdpimamgkj" # Google docs
    #   "ghbmnnjooekpmoecnnnilnnbdlolhkhi" # Google docs off-line
    # ];
    defaultSearchProviderEnabled = true;
    defaultSearchProviderSearchURL = "https://www.google.com/search?q={searchTerms}";
    defaultSearchProviderSuggestURL = "https://www.google.com/complete/search?output=chrome&q={searchTerms}";
    extraOpts = {
      # https://chromeenterprise.google/policies/
      AssistantWebEnabled = false;
      AdvancedProtectionAllowed = true;
      AutofillAddressEnabled = false;
      AutofillCreditCardEnabled = false;
      BackgroundModeEnabled = false;
      BookmarkBarEnabled = false;
      BrowserLabsEnabled = false;
      BrowserNetworkTimeQueriesEnabled = false;
      BuiltInDnsClientEnabled = false;
      ClearBrowsingDataOnExitList = [
        "browsing_history"
        "download_history"
        "cached_images_and_files"
      ];
      ClickToCallEnabled = false;
      DefaultBrowserSettingEnabled = false;
      EncryptedClientHelloEnabled = true;
      ImportAutofillFormData = false;
      DnsOverHttpsMode = "automatic";
      ImportBookmarks = false;
      ImportHistory = false;
      ImportHomepage = false;
      ImportSavedPasswords = false;
      ImportSearchEngine = false;
      LensRegionSearchEnabled = false;
      MediaRecommendationsEnabled = false;
      MetricsReportingEnabled = false;
      PaymentMethodQueryEnabled = false;
      PromotionalTabsEnabled = false;
      SideSearchEnabled = false;
      SpellCheckServiceEnabled = false;
      SpellcheckEnabled = false;
      ShoppingListEnabled = false;
      TranslateEnabled = true;
      PasswordManagerEnabled = false;
      CloudPrintProxyEnabled = false;
      ShowHomeButton = true;
      CloudReportingEnabled = false;
      LogUploadEnabled = false;
      SafeBrowsingSurveysEnabled = false;
      DisableSafeBrowsingProceedAnyway = false;
      PrivacySandboxAdMeasurementEnabled = false;
      PrivacySandboxAdTopicsEnabled = false;
      PrivacySandboxPromptEnabled = false;
      PrivacySandboxSiteEnabledAdsEnabled = false;
      PasswordSharingEnabled = false;
      PasswordLeakDetectionEnabled = false;
      ZstdContentEncodingEnabled = true;
      HighEfficiencyModeEnabled = true;
      HardwareAccelerationModeEnabled = true;
      GoogleSearchSidePanelEnabled = false;
      FeedbackSurveysEnabled = false;
    };
    initialPrefs = {
      autofill = {
        credit_card_enabled = false;
        profile_enabled = false;
      };
      bookmark_bar = {
        show_on_all_tabs = false;
        show_tab_groups = false;
      };
      browser = {
        clear_data = {
          cookies = false;
          cookies_basic = false;
          time_period = 4;
          time_period_basic = 4;
        };
        enable_spellchecking = false;
        has_seen_welcome_page = false;
        last_clear_browsing_data_tab = 1;
        show_home_button = true;
        theme = {
          color_variant = 1;
          user_color = -16711936;
        };
      };
      credentials_enable_autosignin = false;
      credentials_enable_service = false;
      https_only_mode_auto_enabled = false;
      https_only_mode_enabled = true;
      intl.selected_languages = "zh-CN,zh";
      payments.can_make_payment_enabled = false;
      privacy_guide.viewed = true;
      privacy_sandbox.first_party_sets_data_access_allowed_initialized = true;
      safebrowsing = {
        enabled = false;
        enhanced = false;
        esb_enabled_via_tailored_security = false;
        esb_opt_in_with_friendlier_settings = true;
      };
      search.suggest_enabled = true;
      tracking_protection.tracking_protection_3pcd_enabled = false;
      translate.enabled = false;
      adblock.enabled = false;
      auto_pin_new_tab_groups = false;
      download.prompt_for_download = false;
      extensions = {
        alerts.initialized = true;
        ui.developer_mode = true;
      };
      filtering.configurations.adblock.enabled = false;
      history.expire_days_threshold = 0;
      profile = {
        name = "ix";
        avatar_index = 31;
        default_content_setting_values = {
          autoplay = 1;
          idle_detection = 2;
          javascript_jit = 1;
          webgl = 1;
        };
      };
      saved_tab_groups.did_enable_shared_tab_groups_in_last_session = false;
      toolbar.pinned_actions = [ "kActionShowDownloads" ];
    };
  };
}

{ ... }:

{
  i18n.inputMethod.fcitx5.settings = {
    inputMethod = {
      GroupOrder."0" = "Default";
      "Groups/0" = {
        "Default Layout" = "us";
        DefaultIM = "pinyin";
        Name = "Default";
      };
      "Groups/0/Items/0" = {
        Name = "keyboard-us";
        "Layout" = "";
      };
      "Groups/0/Items/1" = {
        Name = "pinyin";
        "Layout" = "";
      };
    };
    globalOptions = {
      Hotkey = {
        EnumerateWithTriggerKeys = "True";
        EnumerateSkipFirst = "False";
      };
      "Hotkey/TriggerKeys" = {
        "0" = "Zenkaku_Hankaku";
        "1" = "Hangul";
        "2" = "Shift+Shift_L";
        "3" = "Shift+Shift_R";
      };
      "Hotkey/EnumerateGroupForwardKeys"."0" = "Super+space";
      "Hotkey/EnumerateGroupBackwardKeys"."0" = "Shift+Super+space";
      "Hotkey/ActivateKeys"."0" = "Hangul_Hanja";
      "Hotkey/DeactivateKeys"."0" = "Hangul_Romaja";
      "Hotkey/PrevPage" = {
        "0" = "Up";
        "1" = "Page_Up";
      };
      "Hotkey/NextPage" = {
        "0" = "Down";
        "1" = "Next";
      };
      "Hotkey/PrevCandidate"."0" = "Shift+Tab";
      "Hotkey/NextCandidate"."0" = "Tab";
      "Hotkey/TogglePreedit"."0" = "Control+Alt+P";
      Behavior = {
        ActiveByDefault = "False";
        ShareInputState = "Program";
        PreeditEnabledByDefault = "True";
        ShowInputMethodInformation = "True";
        showInputMethodInformationWhenFocusIn = "False";
        CompactInputMethodInformation = "True";
        ShowFirstInputMethodInformation = "True";
        DefaultPageSize = "9";
        OverrideXkbOption = "False";
        PreloadInputMethod = "True";
        AllowInputMethodForPassword = "True";
        ShowPreeditForPassword = "False";
        AutoSavePeriod = "99999";
      };
    };
    addons = {
      classicui.globalSection = {
        VerticalCandidateList = "False";
        WheelForPaging = "True";
        Font = "\"更纱黑体 UI SC 14\"";
        MenuFont = "\"更纱黑体 UI SC 14\"";
        TrayFont = "\"更纱黑体 UI SC 14\"";
        TrayOutlineColor = "#000000";
        TrayTextColor = "#ffffff";
        PreferTextIcon = "False";
        ShowLayoutNameInIcon = "True";
        UseInputMethodLanguageToDisplayText = "True";
        Theme = "default";
        DarkTheme = "default-dark";
        UseDarkTheme = "True";
        UseAccentColor = "True";
        PerScreenDPI = "False";
        ForceWaylandDPI = 0;
        EnableFractionalScale = "True";
      };
      clipboard = {
        globalSection."Number of entries" = 18;
        sections."TriggerKey"."0" = "Super+V";
      };
      keyboard = {
        globalSection = {
          PageSize = 9;
          EnableEmoji = "False";
          EnableQuickPhraseEmoji = "False";
          ChooseModifier = "Alt";
          EnableHintByDefault = "False";
          UseNewComposeBehavior = "True";
          EnableLongPress = "False";
        };
        sections = {
          PrevCandidate."0" = "Shift+Tab";
          NextCandidate."0" = "Tab";
          "Hint Trigger"."0" = "Control+Alt+H";
          "One Time Hint Trigger"."0" = "Control+Alt+J";
          LongPressBlocklist."0" = "konsole";
        };
      };
      pinyin = {
        globalSection = {
          ShuangpinProfile = "Ziranma";
          ShowShuangpinMode = "True";
          PageSize = 9;
          SpellEnabled = "False";
          SymbolsEnabled = "False";
          ChaiziEnabled = "True";
          ExtBEnabled = "True";
          CloudPinyinEnabled = "False";
          CloudPinyinIndex = 2;
          CloudPinyinAnimation = "True";
          KeepCloudPinyinPlaceHolder = "False";
          PreeditMode = "\"Composing pinyin\"";
          PreeditCursorPositionAtBeginning = "True";
          PinyinInPreedit = "False";
          Prediction = "False";
          PredictionSize = 10;
          SwitchInputMethodBehavior = "\"Commit current preedit\"";
          SecondCandidate = "";
          ThirdCandidate = "";
          UseKeypadAsSelection = "False";
          BackSpaceToUnselect = "True";
          "Number of sentence" = 2;
          LongWordLengthLimit = 4;
          VAsQuickphrase = "False";
          FirstRun = "False";
          QuickPhraseKey = "";
        };
        sections = {
          ForgetWord."0" = "Control+7";
          PrevPage = {
            "0" = "minus";
            "1" = "Up";
            "2" = "KP_Up";
            "3" = "Page_Up";
          };
          NextPage = {
            "0" = "equal";
            "1" = "Down";
            "2" = "KP_Down";
            "3" = "Next";
          };
          PrevCandidate."0" = "Shift+Tab";
          NextCandidate."0" = "Tab";
          ChooseCharFromPhrase = {
            "0" = "bracketleft";
            "1" = "bracketright";
          };
          FilterByStroke."0" = "grave";
          "QuickPhrase trigger" = {
            "0" = "www.";
            "1" = "ftp.";
            "2" = "http:";
            "3" = "mail.";
            "4" = "bbs.";
            "5" = "forum.";
            "6" = "https:";
            "7" = "ftp:";
            "8" = "telnet:";
            "9" = "mailto:";
          };
          Fuzzy = {
            VE_UE = "True";
            NG_GN = "True";
            Inner = "True";
            InnerShort = "True";
            PartialFinal = "True";
            PartialSp = "False";
            V_U = "True";
            AN_ANG = "True";
            EN_ENG = "True";
            IAN_IANG = "True";
            IN_ING = "True";
            U_OU = "True";
            UAN_UANG = "True";
            C_CH = "True";
            F_H = "True";
            L_N = "True";
            S_SH = "True";
            Z_ZH = "True";
            Correction = "None";
          };
        };
      };
      punctuation = {
        globalSection = {
          HalfWidthPuncAfterLetterOrNumber = "True";
          TypePairedPunctuationsTogether = "False";
          Enabled = "True";
        };
        sections.Hotkey."0" = "Control+period";
      };
      quickphrase = {
        globalSection = {
          ChooseModifier = "None";
          Spell = "False";
          FallbackSpellLanguage = "en";
        };
        sections.TriggerKey = {
          "0" = "Super+grave";
          "1" = "Super+semicolon";
        };
      };
    };
  };
}

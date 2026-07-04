/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class STTRecorderField extends Component {
    static template = "hospital_management.STTRecorderField";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");

        this.state = useState({
            isListening: false,
            isTranslating: false,
            supported: true,
            selectedLanguage: "en-US",
            error: null,
        });

        this.recognition = null;
        this.initialText = "";

        const SpeechRecognition = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
        if (!SpeechRecognition) {
            this.state.supported = false;
        }

        // Bind functions
        this.startListening = this.startListening.bind(this);
        this.stopListening = this.stopListening.bind(this);
        this.clearTranscript = this.clearTranscript.bind(this);
        this.onLanguageChange = this.onLanguageChange.bind(this);
        this.translateTranscript = this.translateTranscript.bind(this);

        onWillUnmount(() => {
            this.stopListening();
        });
    }

    onLanguageChange(ev) {
        this.state.selectedLanguage = ev.target.value;
        if (this.state.isListening) {
            this.stopListening();
            this.startListening();
        }
    }

    startListening() {
        if (!this.state.supported) return;
        this.state.error = null;
        
        // Grab current text and make sure we have spacing if it's not empty
        this.initialText = this.props.record.data[this.props.name] || "";
        if (this.initialText && !this.initialText.endsWith(" ")) {
            this.initialText += " ";
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        this.recognition = new SpeechRecognition();
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.lang = this.state.selectedLanguage;

        this.recognition.onstart = () => {
            this.state.isListening = true;
        };

        this.recognition.onresult = (event) => {
            let finalTranscript = "";
            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    finalTranscript += event.results[i][0].transcript;
                }
            }
            if (finalTranscript) {
                const currentText = this.initialText + finalTranscript;
                this.props.record.update({ [this.props.name]: currentText });
            }
        };

        this.recognition.onerror = (event) => {
            console.error("Speech recognition error:", event.error);
            if (event.error === 'not-allowed') {
                this.state.error = "Microphone access blocked. Please check your browser permissions.";
            } else if (event.error === 'no-speech') {
                // Ignore no-speech error during continuous listening as it triggers easily
            } else {
                this.state.error = `Speech Recognition Error: ${event.error}`;
            }
            this.state.isListening = false;
        };

        this.recognition.onend = () => {
            this.state.isListening = false;
        };

        try {
            this.recognition.start();
        } catch (err) {
            console.error("Failed to start speech recognition:", err);
            this.state.error = err.message || "Failed to start recording.";
            this.state.isListening = false;
        }
    }

    async stopListening() {
        if (this.recognition) {
            try {
                this.recognition.stop();
            } catch (err) {
                console.error("Error stopping recognition:", err);
            }
            this.state.isListening = false;

            // Trigger translation if language is Malayalam and there is content
            const currentText = this.props.record.data[this.props.name] || "";
            if (this.state.selectedLanguage === "ml-IN" && currentText.trim()) {
                await this.translateTranscript(currentText);
            }
        }
    }

    async translateTranscript(text) {
        if (!text || !text.trim()) return;
        this.state.isTranslating = true;
        this.state.error = null;
        try {
            const translatedText = await this.orm.call(
                "hospital.op",
                "translate_text_to_english",
                [text]
            );
            if (translatedText) {
                await this.props.record.update({ [this.props.name]: translatedText });
            }
        } catch (err) {
            console.error("Translation error:", err);
            this.state.error = "Failed to translate Malayalam to English: " + (err.message || err.data?.message || err);
        } finally {
            this.state.isTranslating = false;
        }
    }

    clearTranscript() {
        this.stopListening();
        this.props.record.update({ [this.props.name]: "" });
    }
}

registry.category("fields").add("stt_recorder", {
    component: STTRecorderField,
});

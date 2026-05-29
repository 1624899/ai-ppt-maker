window.PptModelFormDefaults = (() => {
  const DEFAULT_BASE_URL = "https://your-api-endpoint.com/v1";

  function createModelDefaults(modelType) {
    if (modelType === "chat") {
      return {
        name: "新的对话模型",
        base_url: DEFAULT_BASE_URL,
        api_key: "",
        model: "",
        temperature: 0.3,
        max_tokens: 5000,
      };
    }
    return {
      name: "新的生图模型",
      base_url: DEFAULT_BASE_URL,
      api_key: "",
      model: "",
      output_format: "png",
    };
  }

  return {
    DEFAULT_BASE_URL,
    createModelDefaults,
  };
})();

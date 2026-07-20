const DEFAULT_API_BASE = "/api";

const cacheBustVersionMeta = document.querySelector('meta[name="cache-bust-version"]');
const CACHE_BUST_VERSION = cacheBustVersionMeta?.content || "dev";

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register(`/service-worker.js?v=${encodeURIComponent(CACHE_BUST_VERSION)}`)
      .then((registration) => {
        registration.addEventListener("updatefound", () => {
          const installingWorker = registration.installing;
          if (!installingWorker) return;
          installingWorker.addEventListener("statechange", () => {
            if (installingWorker.state === "installed" && registration.waiting) {
              registration.waiting.postMessage({ type: "SKIP_WAITING" });
            }
          });
        });
      })
      .catch((error) => {
        console.warn("Service worker registration failed", error);
      });
  });
}

const APP_BUILD_VERSION = `1.0.0 (${CACHE_BUST_VERSION})`;
console.info("Recipe Clipper frontend", APP_BUILD_VERSION);

function resolveApiBase() {
  return DEFAULT_API_BASE;
}

const API_BASE = resolveApiBase();
const appShell = document.querySelector(".app-shell");
const appShellParent = appShell?.parentElement || null;
const appShellDetachedContainer = document.createDocumentFragment();
const authScreen = document.getElementById("auth-screen");
const loginForm = document.getElementById("login-form");
const loginEmailInput = document.getElementById("login-email");
const loginPasswordInput = document.getElementById("login-password");
const loginError = document.getElementById("login-error");
const logoutButton = document.getElementById("logout-button");
const appBuildVersionLabel = document.getElementById("app-build-version");

const form = document.getElementById("recipe-form");
const submitButton = document.getElementById("submit-button");
const titleInput = document.getElementById("title");
const urlInput = document.getElementById("url");
const sourceAppInput = document.getElementById("source_app");
const sourceTypeInput = document.getElementById("source_type");
const imageUrlInput = document.getElementById("image_url");
const notesInput = document.getElementById("notes");
const tagsInput = document.getElementById("tags");
const editIdInput = document.getElementById("edit-id");
const recipesContainer = document.getElementById("recipes");
const refreshButton = document.getElementById("refresh-button");
const cancelEditButton = document.getElementById("cancel-edit-button");
const statusMessage = document.getElementById("status-message");
const shareImportPanel = document.getElementById("share-import-panel");
const shareImportLabel = document.getElementById("share-import-label");
const shareImportTitle = document.getElementById("share-import-title");
const shareImportDetails = document.getElementById("share-import-details");
const shareImportActions = document.getElementById("share-import-actions");
const shareImportOpenButton = document.getElementById("share-import-open-button");
const shareImportManualButton = document.getElementById("share-import-manual-button");
const shareImportPreview = document.getElementById("share-import-preview");
const shareImportPreviewImage = document.getElementById("share-import-preview-image");
const shareImportPreviewCaption = document.getElementById("share-import-preview-caption");
const parsedServingsEl = document.getElementById("parsed-servings");
const parsedIngredientsEl = document.getElementById("parsed-ingredients");
const parsedInstructionsEl = document.getElementById("parsed-instructions");
const parsedResultsSection = document.getElementById("parsed-results");
const parsedServingsSection = document.getElementById("parsed-servings-section");
const parsedIngredientsSection = document.getElementById("parsed-ingredients-section");
const parsedInstructionsSection = document.getElementById("parsed-instructions-section");
const ocrWarningBanner = document.getElementById("ocr-warning-banner");
const recipeDetailView = document.getElementById("recipe-detail-view");
const closeDetailButton = document.getElementById("close-detail-button");
const detailTitleEl = document.getElementById("detail-title");
const detailReviewStatusEl = document.getElementById("detail-review-status");
const detailAiCleanupStatusEl = document.getElementById("detail-ai-cleanup-status");
const detailAiCleanupButton = document.getElementById("detail-ai-cleanup-button");
const detailImageWrapEl = document.getElementById("detail-image-wrap");
const detailImageEl = document.getElementById("detail-image");
const detailPrepTimeEl = document.getElementById("detail-prep-time");
const detailCookTimeEl = document.getElementById("detail-cook-time");
const detailMetaRowEl = document.getElementById("detail-meta-row");
const detailIngredientsEl = document.getElementById("detail-ingredients");
const detailServingsValueEl = document.getElementById("detail-servings-value");
const detailServingsDecreaseButton = document.getElementById("detail-servings-decrease");
const detailServingsIncreaseButton = document.getElementById("detail-servings-increase");
const detailConvertButton = document.getElementById("detail-convert-button");
const detailConvertValueEl = document.getElementById("detail-convert-value");
const detailConvertMenu = document.getElementById("detail-convert-menu");
const detailRecipeNotesSectionEl = document.getElementById("detail-recipe-notes-section");
const detailRecipeNotesEl = document.getElementById("detail-recipe-notes");
const detailInstructionsEl = document.getElementById("detail-instructions");
const copyIngredientsButton = document.getElementById("copy-ingredients-button");
const detailGroceriesButton = document.getElementById("detail-groceries-button");
const detailShareButton = document.getElementById("detail-share-button");
const openOriginalButton = document.getElementById("open-original-button");
const detailEditButton = document.getElementById("detail-edit-button");
const detailMenuButton = document.getElementById("detail-menu-button");
const detailActionsMenu = document.getElementById("detail-actions-menu");
const detailMenuEditButton = document.getElementById("detail-menu-edit-button");
const detailMenuDeleteButton = document.getElementById("detail-menu-delete-button");
const detailCookedToggle = document.getElementById("detail-cooked-toggle");
const detailRatingStars = document.getElementById("detail-rating-stars");
const detailNoteInput = document.getElementById("detail-note-input");
const detailSourceLinksEl = document.getElementById("detail-source-links");
const detailSourceRecipeLinkEl = document.getElementById("detail-source-recipe-link");
const detailImportedFromLinkEl = document.getElementById("detail-imported-from-link");
const detailCookbookMembership = document.getElementById("detail-cookbook-membership");
const detailCookbookAddButton = document.getElementById("detail-cookbook-add-button");
const detailCookbookPopover = document.getElementById("detail-cookbook-popover");
const detailCookbookOptions = document.getElementById("detail-cookbook-options");
const detailCookbookSaveButton = document.getElementById("detail-cookbook-save-button");
const detailNewCookbookButton = document.getElementById("detail-new-cookbook-button");
const recipesListHeader = document.getElementById("recipes-list-header");
const cookbookView = document.getElementById("cookbook-view");
const cookbooksPanel = document.getElementById("cookbooks-panel");
const dashboardMainPanel = document.getElementById("dashboard-main-panel");
const selectedCookbookTitle = document.getElementById("selected-cookbook-title");
const backToCookbooksButton = document.getElementById("back-to-cookbooks-button");
const emptyState = document.getElementById("empty-state");
const pageContainer = document.querySelector(".container");
const searchInput = document.getElementById("search-input");
const cookbookSearchInput = document.getElementById("cookbook-search-input");
const detailImagePlaceholderEl = document.getElementById("detail-image-placeholder");
const cookbookGrid = document.getElementById("cookbook-grid");
const selectedCookbookCount = document.getElementById("selected-cookbook-count");
const cookbookMenuButton = document.getElementById("cookbook-menu-button");
const cookbookActionsMenu = document.getElementById("cookbook-actions-menu");
const renameCookbookButton = document.getElementById("rename-cookbook-button");
const deleteCookbookButton = document.getElementById("delete-cookbook-button");
const dashboardSearchPanel = document.getElementById("dashboard-search-panel");
const dashboardSearchResults = document.getElementById("dashboard-search-results");
const dashboardSearchEmptyState = document.getElementById("dashboard-search-empty-state");
const sidePanel = document.getElementById("side-panel");
const sideCookbookList = document.getElementById("side-cookbook-list");
const sideCookbookSection = document.querySelector(".side-nav-section");
const cookbooksSectionToggle = document.getElementById("cookbooks-section-toggle");
const navCookbooksButton = document.getElementById("nav-cookbooks-button");
const navMealPlanButton = document.getElementById("nav-meal-plan-button");
const navGroceriesButton = document.getElementById("nav-groceries-button");
const mobileBottomNav = document.getElementById("mobile-bottom-nav");
const mobileBottomNavParent = mobileBottomNav?.parentElement || null;
const mobileBottomNavDetachedContainer = document.createDocumentFragment();
const mobileNavRecipesButton = mobileBottomNav?.querySelector("[data-nav=\"recipes\"]");
const mobileNavMealPlanButton = mobileBottomNav?.querySelector("[data-nav=\"meal-plan\"]");
const mobileNavGroceriesButton = mobileBottomNav?.querySelector("[data-nav=\"groceries\"]");
const mobileAddButton = document.getElementById("mobile-add-button");
const navAdminUsersButton = document.getElementById("nav-admin-users-button");
const navSettingsButton = document.getElementById("nav-settings-button");
const brandHomeButton = document.getElementById("brand-home-button");
const sidebarToggleButtons = Array.from(document.querySelectorAll("[data-sidebar-toggle]"));
const adminUsersPanel = document.getElementById("admin-users-panel");
const adminUsersStatus = document.getElementById("admin-users-status");
const adminUsersTableWrap = document.getElementById("admin-users-table-wrap");
const adminUsersAccessRequired = document.getElementById("admin-users-access-required");
const adminAddUserForm = document.getElementById("admin-add-user-form");
const adminUserEmailInput = document.getElementById("admin-user-email");
const adminUserDisplayNameInput = document.getElementById("admin-user-display-name");
const adminUserPasswordInput = document.getElementById("admin-user-password");
const adminUserIsAdminInput = document.getElementById("admin-user-is-admin");
const adminSecuritySettingsForm = document.getElementById("admin-security-settings-form");
const settingsPanel = document.getElementById("settings-panel");
const settingsStatus = document.getElementById("settings-status");
const facebookCookieInput = document.getElementById("facebook-cookie-input");
const facebookCookieState = document.getElementById("facebook-cookie-state");
const facebookCookieSaveButton = document.getElementById("facebook-cookie-save-button");
const facebookCookieClearButton = document.getElementById("facebook-cookie-clear-button");
const facebookCookieTestButton = document.getElementById("facebook-cookie-test-button");
const facebookCookieTestState = document.getElementById("facebook-cookie-test-state");
const importServicesWarning = document.getElementById("import-services-warning");
const importServicesStatusList = document.getElementById("import-services-status-list");
const authLockoutEnabledInput = document.getElementById("auth-lockout-enabled");
const authMaxFailedAttemptsInput = document.getElementById("auth-max-failed-attempts");
const authLockoutMinutesInput = document.getElementById("auth-lockout-minutes");
const REVIEW_STATUS_POLL_INTERVAL_MS = 4000;
let reviewStatusPollTimer = null;
let detailAiCleanupState = "idle";
let importProgressTimer = null;

const openAddRecipeButton = document.getElementById("open-add-recipe-button");
const openAddRecipeRailButton = document.getElementById("open-add-recipe-rail-button");
const closeAddRecipeButton = document.getElementById("close-add-recipe-button");
const addRecipeModal = document.getElementById("add-recipe-modal");
const addRecipeModalParent = addRecipeModal?.parentElement || null;
const addRecipeModalDetachedContainer = document.createDocumentFragment();
const addRecipeModalTitle = document.getElementById("add-recipe-modal-title");
const importBrowserPanel = document.getElementById("import-browser-panel");
const importModeBackButton = document.getElementById("import-mode-back-button");
const importModeSeparator = document.getElementById("import-mode-separator");
const importUrlRow = document.getElementById("import-url-row");
const importDivider = document.getElementById("import-divider");
const importOptionGrid = document.getElementById("import-option-grid");
const browserOptionButton = document.getElementById("browser-option-button");
const addRecipeStatus = document.getElementById("add-recipe-status");
const runAiCleanupButton = document.getElementById("run-ai-cleanup-button");
const addRecipeSubmitButton = document.getElementById("add-recipe-submit-button");
const bottomSaveRecipeButton = document.getElementById("bottom-save-recipe-button");
const parsedResultsTitle = document.getElementById("parsed-results-title");
const editFieldsPanel = document.getElementById("edit-fields-panel");
const editTitleInput = document.getElementById("edit-title-input");
const editServingsInput = document.getElementById("edit-servings-input");
const editPrepTimeInput = document.getElementById("edit-prep-time-input");
const editCookTimeInput = document.getElementById("edit-cook-time-input");
const editImagePanel = document.getElementById("edit-image-panel");
const editImagePreview = document.getElementById("edit-image-preview");
const editImagePlaceholder = document.getElementById("edit-image-placeholder");
const editImageInput = document.getElementById("edit-image-input");
const clearEditImageButton = document.getElementById("clear-edit-image-button");
const addIngredientButton = document.getElementById("add-ingredient-button");
const addIngredientSectionButton = document.getElementById("add-ingredient-section-button");
const addInstructionButton = document.getElementById("add-instruction-button");
const addInstructionSectionButton = document.getElementById("add-instruction-section-button");
const ingredientsReorderButton = document.getElementById("ingredients-reorder-button");
const instructionsReorderButton = document.getElementById("instructions-reorder-button");
const pasteTextOptionButton = document.getElementById("paste-text-option-button");
const pasteTextPanel = document.getElementById("paste-text-panel");
const pasteRecipeTextInput = document.getElementById("paste-recipe-text");
const pasteTextImportButton = document.getElementById("paste-text-import-button");
const uploadPhotoButton = document.getElementById("upload-photo-button");
const writeFromScratchOptionButton = document.getElementById("write-from-scratch-option-button");
const imageUploadInput = document.getElementById("image-upload-input");
const shoppingSelectionToggle = document.getElementById("shopping-selection-toggle");
const selectAllRecipesButton = document.getElementById("select-all-recipes-button");
const shoppingSelectionCount = document.getElementById("shopping-selection-count");
const generateShoppingListButton = document.getElementById("generate-shopping-list-button");
const moveSelectedRecipesButton = document.getElementById("move-selected-recipes-button");
const deleteSelectedRecipesButton = document.getElementById("delete-selected-recipes-button");
const shoppingListView = document.getElementById("shopping-list-view");
const shoppingListItems = document.getElementById("shopping-list-items");
const shoppingListCount = document.getElementById("shopping-list-count");
const shoppingListStatus = document.getElementById("shopping-list-status");
const closeShoppingListButton = document.getElementById("close-shopping-list-button");
const grocerySourceCards = document.getElementById("grocery-source-cards");
const checkedGrocerySection = document.getElementById("checked-grocery-section");
const checkedGroceryItems = document.getElementById("checked-grocery-items");
const checkedGroceryCount = document.getElementById("checked-grocery-count");
const clearCheckedGroceryButton = document.getElementById("clear-checked-grocery-button");
const clearGroceryListButton = document.getElementById("clear-grocery-list-button");
const groceryPreviewModal = document.getElementById("grocery-preview-modal");
const closeGroceryPreviewButton = document.getElementById("close-grocery-preview-button");
const groceryPreviewItems = document.getElementById("grocery-preview-items");
const groceryPreviewStatus = document.getElementById("grocery-preview-status");
const confirmGroceryPreviewButton = document.getElementById("confirm-grocery-preview-button");
const aiCleanupReviewModal = document.getElementById("ai-cleanup-review-modal");
const closeAiCleanupReviewButton = document.getElementById("close-ai-cleanup-review-button");
const aiCleanupReviewStatus = document.getElementById("ai-cleanup-review-status");
const aiCleanupReviewChanges = document.getElementById("ai-cleanup-review-changes");
const cancelAiCleanupReviewButton = document.getElementById("cancel-ai-cleanup-review-button");
const acceptAiCleanupReviewButton = document.getElementById("accept-ai-cleanup-review-button");
const mealPlanView = document.getElementById("meal-plan-view");
const mealPlanWeekRange = document.getElementById("meal-plan-week-range");
const mealPlanStatus = document.getElementById("meal-plan-status");
const mealPlanDays = document.getElementById("meal-plan-days");
const mealPlanPrevWeekButton = document.getElementById("meal-plan-prev-week");
const mealPlanThisWeekButton = document.getElementById("meal-plan-this-week");
const mealPlanNextWeekButton = document.getElementById("meal-plan-next-week");
const mealPlanGroceryButton = document.getElementById("meal-plan-grocery-button");
const shareModal = document.getElementById("share-modal");
const closeShareModalButton = document.getElementById("close-share-modal-button");
const shareTextButton = document.getElementById("share-text-button");
const copyTextButton = document.getElementById("copy-text-button");
const printRecipeButton = document.getElementById("print-recipe-button");
const mealPlanAddModal = document.getElementById("meal-plan-add-modal");
const closeMealPlanAddModalButton = document.getElementById("close-meal-plan-add-modal");
const cancelMealPlanAddButton = document.getElementById("cancel-meal-plan-add");
const confirmMealPlanAddButton = document.getElementById("confirm-meal-plan-add");
const mealPlanAddDateLabel = document.getElementById("meal-plan-add-date-label");
const mealPlanAddHelper = document.getElementById("meal-plan-add-helper");
const mealPlanDateInput = document.getElementById("meal-plan-date-input");
const mealPlanRecipeSelect = document.getElementById("meal-plan-recipe-select");
const mealPlanSlotSelect = document.getElementById("meal-plan-slot-select");
const socialResolutionDebug = document.getElementById("social-resolution-debug");
const socialDebugOriginalUrl = document.getElementById("social-debug-original-url");
const socialDebugCanonicalUrl = document.getElementById("social-debug-canonical-url");
const socialDebugPostId = document.getElementById("social-debug-post-id");
const socialDebugMethod = document.getElementById("social-debug-method");
const socialDebugResolvedUrl = document.getElementById("social-debug-resolved-url");
const submitButtonDefaultLabel = submitButton ? submitButton.textContent : "→";

const formState = {
  parsed: {
    image_url: "",
    servings: "",
    prep_time: "",
    cook_time: "",
    total_time: "",
    prep_minutes: null,
    cook_minutes: null,
    total_minutes: null,
    ingredients: [],
    instructions: [],
    ingredient_groups: [],
    instruction_groups: [],
    metadata_extracted: false,
    ocr_confidence: null,
    ocr_warning: "",
    ocr_warning_level: ""
  },
  import_context: {
    original_url: "",
    resolved_url: "",
    original_source_url: "",
    resolved_recipe_url: "",
    content_source: ""
  },
  selectedRecipe: null
};

if (appBuildVersionLabel) {
  appBuildVersionLabel.textContent = `Recipe Clipper ${APP_BUILD_VERSION}`;
}

let allRecipes = [];
let selectedCookbook = "";
let currentView = "dashboard";
let shareImportOpenRecipeId = null;
let shareImportManualPayload = null;
let allCookbooks = [];
let sidePanelExpanded = true;
let cookbooksSectionExpanded = true;
let cookbookActionsMenuOpen = false;
let detailActionsMenuOpen = false;
let detailCookbookPopoverOpen = false;
let detailCookbookDraftSelection = new Set();
let detailConvertMenuOpen = false;
let adminUsers = [];
const UNCATEGORIZED_COOKBOOK_ID = "__uncategorized__";
const MEASUREMENT_MODE_STORAGE_KEY = "recipeClipper.measurementMode";
let isImportLoading = false;
let isModalAiCleanupRunning = false;
let isRecipeSaving = false;
let addRecipeMode = "choose";
let shoppingSelectionMode = false;
let selectedShoppingRecipeIds = new Set();
let pendingGroceryPreviewItems = [];
let pendingAiCleanupReview = null;
let ingredientReorderMode = false;
let instructionReorderMode = false;
let pendingIngredientFocusIndex = null;
let pendingInstructionFocusIndex = null;
let mealPlanStartDate = getMondayDate(new Date());
let pendingMealPlanDate = "";
let detailIngredientDisplayState = {
  baseServings: 1,
  targetServings: 1,
  convertMode: "original"
};

let detailStateSaveTimer = null;
let currentDetailRecipeId = "";

function getMondayDate(date) {
  const d = new Date(date);
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

function formatIsoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatWeekRange(startDateText, endDateText) {
  const start = new Date(`${startDateText}T00:00:00`);
  const end = new Date(`${endDateText}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return `${startDateText} to ${endDateText}`;
  const startMonth = start.toLocaleDateString(undefined, { month: "short" });
  const endMonth = end.toLocaleDateString(undefined, { month: "short" });
  const startDay = start.getDate();
  const endDay = end.getDate();
  if (startMonth === endMonth && start.getFullYear() === end.getFullYear()) {
    return `${startDay} ${startMonth} ${start.getFullYear()} - ${endDay} ${endMonth} ${end.getFullYear()}`;
  }
  return `${startDay} ${startMonth} ${start.getFullYear()} - ${endDay} ${endMonth} ${end.getFullYear()}`;
}
function formatMealSlotLabel(slot) {
  const normalized = String(slot || "dinner").toLowerCase();
  if (normalized === "breakfast") return "Breakfast";
  if (normalized === "lunch") return "Lunch";
  if (normalized === "other") return "Other";
  return "Dinner";
}

function formatMealPlanDayLabel(dateText) {
  const date = new Date(`${dateText}T00:00:00`);
  if (Number.isNaN(date.getTime())) return "";
  const weekday = date.toLocaleDateString(undefined, { weekday: "long" });
  return `${weekday} ${date.getDate()}`;
}
let currentUser = null;
let adminSecuritySettings = {
  auth_lockout_enabled: true,
  auth_max_failed_attempts: 5,
  auth_lockout_minutes: 15
};
const MOBILE_SIDEBAR_MEDIA_QUERY = "(max-width: 760px)";

function userCanAccessAdminUsersView() {
  return currentUser?.is_admin === true;
}

function enforceAdminUsersViewGuard() {
  if (currentView !== "admin-users") return false;
  if (userCanAccessAdminUsersView()) return false;
  navigateToDashboardHome();
  return true;
}

function isAuthenticated() {
  return Boolean(currentUser);
}

function setAuthView(authed) {
  const authenticated = Boolean(authed);
  if (!authenticated) {
    hideAddRecipeModal();
    closeOpenModalsForMobileNav();
  }
  if (authenticated) {
    if (appShellParent && appShell && !appShell.isConnected) {
      appShellParent.appendChild(appShell);
    }
    if (mobileBottomNavParent && mobileBottomNav && !mobileBottomNav.isConnected) {
      mobileBottomNavParent.appendChild(mobileBottomNav);
    }
    if (addRecipeModalParent && addRecipeModal && !addRecipeModal.isConnected) {
      addRecipeModalParent.appendChild(addRecipeModal);
    }
  } else {
    if (appShell && appShell.isConnected) {
      appShellDetachedContainer.appendChild(appShell);
    }
    if (mobileBottomNav && mobileBottomNav.isConnected) {
      mobileBottomNavDetachedContainer.appendChild(mobileBottomNav);
    }
    if (addRecipeModal && addRecipeModal.isConnected) {
      addRecipeModalDetachedContainer.appendChild(addRecipeModal);
    }
  }
  if (authScreen) authScreen.classList.toggle("hidden", authenticated);
}

async function rawApiFetch(url, options = {}) {
  return fetch(url, {
    credentials: "include",
    ...options
  });
}

function handleUnauthorized() {
  currentUser = null;
  adminUsers = [];
  setAdminUsersAccessState();
  setAuthView(false);
}

function setAdminUsersAccessState() {
  const isAdmin = userCanAccessAdminUsersView();
  if (navAdminUsersButton) {
    navAdminUsersButton.classList.toggle("hidden", !isAdmin);
  }
  if (adminUsersAccessRequired) {
    adminUsersAccessRequired.classList.toggle("hidden", isAdmin);
  }
  if (adminAddUserForm) {
    adminAddUserForm.classList.toggle("hidden", !isAdmin);
  }
  if (adminSecuritySettingsForm) {
    adminSecuritySettingsForm.classList.toggle("hidden", !isAdmin);
  }
  if (adminUsersTableWrap) {
    adminUsersTableWrap.classList.toggle("hidden", !isAdmin);
    if (!isAdmin) adminUsersTableWrap.innerHTML = "";
  }
  if (adminUsersStatus && !isAdmin) {
    adminUsersStatus.classList.add("hidden");
    adminUsersStatus.textContent = "";
  }

  enforceAdminUsersViewGuard();
}

async function apiFetch(url, options = {}) {
  const response = await rawApiFetch(url, options);
  if (response.status === 401 && !String(url).includes("/auth/login")) {
    handleUnauthorized();
  }
  return response;
}

async function checkAuthSession() {
  const response = await rawApiFetch(`${API_BASE}/auth/me`);
  if (!response.ok) {
    handleUnauthorized();
    return false;
  }
  currentUser = await response.json();
  setAdminUsersAccessState();
  enforceAdminUsersViewGuard();
  setAuthView(true);
  return true;
}

function getDefaultSidePanelState() {
  return !window.matchMedia("(max-width: 900px)").matches;
}

function loadSidePanelPreference() {
  if (window.matchMedia(MOBILE_SIDEBAR_MEDIA_QUERY).matches) {
    return false;
  }
  const storedValue = localStorage.getItem("recipe_clipper_sidebar_expanded");
  if (storedValue === "true" || storedValue === "false") {
    return storedValue === "true";
  }
  return getDefaultSidePanelState();
}

function setSidePanelExpanded(nextExpanded, persist = true) {
  sidePanelExpanded = Boolean(nextExpanded);
  if (!sidePanelExpanded && cookbooksSectionExpanded) {
    setCookbooksSectionExpanded(false, persist);
  }
  document.body.classList.toggle("sidebar-collapsed", !sidePanelExpanded);
  if (sidePanel) {
    sidePanel.setAttribute("aria-expanded", sidePanelExpanded ? "true" : "false");
  }
  if (persist) {
    localStorage.setItem("recipe_clipper_sidebar_expanded", String(sidePanelExpanded));
  }
}

function toggleSidePanel() {
  const shouldPersist = !window.matchMedia(MOBILE_SIDEBAR_MEDIA_QUERY).matches;
  setSidePanelExpanded(!sidePanelExpanded, shouldPersist);
}

function setCookbooksSectionExpanded(nextExpanded, persist = true) {
  cookbooksSectionExpanded = Boolean(nextExpanded);
  if (sideCookbookSection) {
    sideCookbookSection.classList.toggle("is-collapsed", !cookbooksSectionExpanded);
  }
  if (cookbooksSectionToggle) {
    cookbooksSectionToggle.setAttribute("aria-expanded", cookbooksSectionExpanded ? "true" : "false");
  }
  if (persist) {
    localStorage.setItem("recipe_clipper_cookbooks_section_expanded", String(cookbooksSectionExpanded));
  }
}

function loadCookbooksSectionPreference() {
  const storedValue = localStorage.getItem("recipe_clipper_cookbooks_section_expanded");
  if (storedValue === "true" || storedValue === "false") {
    return storedValue === "true";
  }
  return getDefaultSidePanelState();
}

function getRecipeDetailState(recipe) {
  if (!recipe) return { cooked: false, rating: 0, note: "" };
  return {
    cooked: Boolean(recipe.is_cooked),
    rating: Number(recipe.rating) || 0,
    note: String(recipe.personal_note || "")
  };
}

function updateRecipeInMemory(recipeId, updates) {
  allRecipes = allRecipes.map((recipe) =>
    String(recipe.id) === String(recipeId) ? { ...recipe, ...updates } : recipe
  );
  if (formState.selectedRecipe && String(formState.selectedRecipe.id) === String(recipeId)) {
    formState.selectedRecipe = { ...formState.selectedRecipe, ...updates };
  }
}

async function saveRecipeUserState(recipeId, partialState) {
  const response = await apiFetch(`${API_BASE}/recipes/${recipeId}/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(partialState)
  });
  if (!response.ok) return null;
  return response.json();
}

function normalizeServingsDisplay(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";

  const pieces = raw
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);

  if (pieces.length < 2) return raw;

  const deduped = [];
  const seen = new Set();

  pieces.forEach((part) => {
    const normalized = part.toLowerCase();
    const normalizedNoPeople = normalized.replace(/\b(people|person|servings?|serves?)\b/g, "").trim();

    if (seen.has(normalized) || (normalizedNoPeople && seen.has(normalizedNoPeople))) {
      return;
    }

    seen.add(normalized);
    if (normalizedNoPeople) seen.add(normalizedNoPeople);
    deduped.push(part);
  });

  return deduped.join(", ");
}

function parseNumberToken(token) {
  const raw = String(token || "").trim();
  if (!raw) return null;
  const value = raw
    .replace(/[\u00BC\u00BD\u00BE\u2150-\u215E]/g, (char) => {
      const map = {
        "\u00BC": "1/4",
        "\u00BD": "1/2",
        "\u00BE": "3/4",
        "\u2150": "1/7",
        "\u2151": "1/9",
        "\u2152": "1/10",
        "\u2153": "1/3",
        "\u2154": "2/3",
        "\u2155": "1/5",
        "\u2156": "2/5",
        "\u2157": "3/5",
        "\u2158": "4/5",
        "\u2159": "1/6",
        "\u215A": "5/6",
        "\u215B": "1/8",
        "\u215C": "3/8",
        "\u215D": "5/8",
        "\u215E": "7/8"
      };
      return map[char] || char;
    })
    .replace(/\s+/g, " ")
    .trim();
  if (!value) return null;
  if (/^\d+\s+\d+\/\d+$/.test(value)) {
    const [whole, fraction] = value.split(/\s+/);
    const [num, den] = fraction.split("/").map(Number);
    if (!den) return null;
    return Number(whole) + (num / den);
  }
  if (/^\d+\/\d+$/.test(value)) {
    const [num, den] = value.split("/").map(Number);
    if (!den) return null;
    return num / den;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseServingsCount(servingsValue) {
  const normalized = normalizeServingsDisplay(servingsValue);
  const matched = normalized.match(/(\d+\s+\d+\/\d+|\d+\/\d+|\d+(?:\.\d+)?)/);
  const parsed = parseNumberToken(matched?.[1] || "");
  if (!parsed || parsed <= 0) return 1;
  return parsed;
}

function formatKitchenQuantity(value) {
  if (!Number.isFinite(value) || value <= 0) return "";
  const roundedWhole = Math.round(value);
  if (Math.abs(value - roundedWhole) < 0.02) return String(roundedWhole);

  const whole = Math.floor(value);
  const fractional = value - whole;
  const denominators = [2, 3, 4, 8];
  let best = null;

  denominators.forEach((den) => {
    const numerator = Math.round(fractional * den);
    if (numerator === 0 || numerator >= den) return;
    const approx = numerator / den;
    const error = Math.abs(fractional - approx);
    if (!best || error < best.error) {
      best = { numerator, den, error };
    }
  });

  if (best && best.error <= 0.08) {
    const prefix = whole > 0 ? `${whole} ` : "";
    return `${prefix}${best.numerator}/${best.den}`;
  }

  const rounded = Math.round(value * 10) / 10;
  return String(rounded).replace(/\.0$/, "");
}

function parseLeadingQuantity(line) {
  const raw = String(line || "");
  const tokens = raw.trim().split(/\s+/);
  if (!tokens.length) return null;

  let consumed = 0;
  let quantity = 0;
  while (consumed < tokens.length) {
    const token = tokens[consumed];
    const parsed = parseNumberToken(token);
    if (parsed === null) break;
    quantity += parsed;
    consumed += 1;
  }

  if (!consumed || quantity <= 0) return null;
  const remaining = tokens.slice(consumed).join(" ");
  if (!remaining) return null;
  return { quantity, remaining };
}

const INGREDIENT_UNIT_ALIASES = [
  { aliases: ["tablespoons", "tablespoon", "tbsp"], singular: "tablespoon", plural: "tablespoons" },
  { aliases: ["teaspoons", "teaspoon", "tsp"], singular: "teaspoon", plural: "teaspoons" },
  { aliases: ["cups", "cup"], singular: "cup", plural: "cups" },
  { aliases: ["fl oz", "fluid ounces", "fluid ounce"], singular: "fl oz", plural: "fl oz" },
  { aliases: ["ounces", "ounce", "oz"], singular: "ounce", plural: "ounces" },
  { aliases: ["pounds", "pound", "lbs", "lb"], singular: "lb", plural: "lbs" },
  { aliases: ["grams", "gram", "g"], singular: "gram", plural: "grams" },
  { aliases: ["kilograms", "kilogram", "kilos", "kilo", "kg"], singular: "kilogram", plural: "kilograms" },
  { aliases: ["milliliters", "milliliter", "millilitres", "millilitre", "ml"], singular: "milliliter", plural: "milliliters" },
  { aliases: ["litres", "litre", "liters", "liter", "l"], singular: "litre", plural: "litres" }
];

const SUSPICIOUS_SINGLE_LETTER_UNIT_WORDS = new Set(["garlic", "green", "large"]);

function parseLeadingUnit(remaining) {
  const text = String(remaining || "").trim();
  if (!text) return null;
  const lower = text.toLowerCase();
  const candidates = INGREDIENT_UNIT_ALIASES
    .flatMap((unit) => unit.aliases.map((alias) => ({ alias, unit })))
    .sort((a, b) => b.alias.length - a.alias.length);
  const matched = candidates.find(({ alias }) =>
    lower.startsWith(alias) && /(?:\s|$|,|\.)/.test(lower.slice(alias.length, alias.length + 1) || " ")
  );
  if (!matched) return null;
  const rest = text.slice(matched.alias.length).trimStart();
  return { ...matched.unit, rest };
}

function convertQuantityAndUnit(quantity, unitInfo, mode) {
  if (!unitInfo || mode === "original") return { quantity, unit: unitInfo };
  const unitName = unitInfo.aliases[0];

  if (mode === "metric") {
    if (["cups", "cup"].includes(unitName)) {
      const ml = quantity * 240;
      return { quantity: ml, unit: { singular: "ml", plural: "ml" } };
    }
    if (["tablespoons", "tablespoon", "tbsp"].includes(unitName)) return { quantity: quantity * 15, unit: { singular: "ml", plural: "ml" } };
    if (["teaspoons", "teaspoon", "tsp"].includes(unitName)) return { quantity: quantity * 5, unit: { singular: "ml", plural: "ml" } };
    if (["fl oz", "fluid ounces", "fluid ounce"].includes(unitName)) return { quantity: quantity * 29.57, unit: { singular: "ml", plural: "ml" } };
    if (["ounces", "ounce", "oz"].includes(unitName)) return { quantity: quantity * 28.35, unit: { singular: "g", plural: "g" } };
    if (["pounds", "pound", "lbs", "lb"].includes(unitName)) return { quantity: quantity * 453.59, unit: { singular: "g", plural: "g" } };
  }

  if (mode === "imperial") {
    if (["grams", "gram", "g"].includes(unitName)) {
      const oz = quantity / 28.35;
      if (oz >= 16) return { quantity: oz / 16, unit: { singular: "lb", plural: "lbs" } };
      return { quantity: oz, unit: { singular: "ounce", plural: "ounces" } };
    }
    if (["kilograms", "kilogram", "kilos", "kilo", "kg"].includes(unitName)) return { quantity: quantity * 2.2046, unit: { singular: "lbs", plural: "lbs" } };
    if (["milliliters", "milliliter", "ml"].includes(unitName)) return { quantity: quantity / 29.57, unit: { singular: "oz", plural: "oz" } };
    if (["litres", "litre", "liters", "liter", "l"].includes(unitName)) {
      const cups = quantity * 4.22675;
      if (cups <= 4) return { quantity: cups, unit: { singular: "cup", plural: "cups" } };
      return { quantity: (quantity * 1000) / 29.57, unit: { singular: "oz", plural: "oz" } };
    }
  }

  return { quantity, unit: unitInfo };
}

function pluralizedUnit(unit, quantity) {
  if (!unit) return "";
  if (unit.singular === unit.plural) return unit.singular;
  const isSingular = quantity < 1.05 || Math.abs(quantity - 1) < 0.05;
  return isSingular ? unit.singular : unit.plural;
}

function shouldMergeSuspiciousSingleLetterUnitFragment(unitToken, nextPart) {
  const normalizedUnit = String(unitToken || "").trim().toLowerCase();
  if (!["g", "l"].includes(normalizedUnit)) return false;
  const nextTokenMatch = String(nextPart || "").trim().match(/^([a-z]+)/i);
  if (!nextTokenMatch) return false;
  return SUSPICIOUS_SINGLE_LETTER_UNIT_WORDS.has(`${normalizedUnit}${nextTokenMatch[1]}`.toLowerCase());
}

function repairSuspiciousSingleLetterUnitFragment(remaining) {
  const text = String(remaining || "").trim();
  const matched = text.match(/^([gl])\s+([a-z]+)(\b.*)$/i);
  if (!matched) return text;
  const [, unitToken, fragment, tail = ""] = matched;
  if (!SUSPICIOUS_SINGLE_LETTER_UNIT_WORDS.has(`${unitToken}${fragment}`.toLowerCase())) {
    return text;
  }
  return `${unitToken}${fragment}${tail}`;
}

function roundMetricQuantity(quantity, unit) {
  if (!Number.isFinite(quantity) || quantity <= 0) return quantity;
  const normalizedUnit = String(unit?.singular || "").toLowerCase();
  if (!["g", "gram", "grams", "ml", "milliliter", "milliliters"].includes(normalizedUnit)) {
    return Math.round(quantity);
  }

  if (quantity >= 1000) return Math.round(quantity / 10) * 10;
  if (quantity >= 100) return Math.round(quantity / 5) * 5;
  if (quantity >= 20) return Math.round(quantity / 5) * 5;
  return Math.round(quantity);
}

function formatDisplayQuantity(value, mode, unit) {
  if (mode === "metric") {
    const roundedMetric = roundMetricQuantity(value, unit);
    if (!Number.isFinite(roundedMetric) || roundedMetric <= 0) return "";
    return String(Math.round(roundedMetric));
  }
  if (mode === "imperial") {
    if (!Number.isFinite(value) || value <= 0) return "";
    const normalizedUnit = String(unit?.singular || unit?.plural || "").toLowerCase();
    if (["lb", "lbs", "pound", "pounds"].includes(normalizedUnit)) {
      const roundedHalf = Math.round(value * 2) / 2;
      if (Math.abs(value - roundedHalf) <= 0.03) {
        return String(roundedHalf).replace(/\.0$/, "");
      }
    }
    const rounded = Math.round(value * 10) / 10;
    return String(rounded).replace(/\.0$/, "");
  }
  return formatKitchenQuantity(value);
}

function getRecipeIngredientDisplayState(recipe) {
  const baseServings = parseServingsCount(recipe?.servings);
  return {
    baseServings,
    targetServings: baseServings,
    convertMode: getRecipeMeasurementMode(recipe)
  };
}

function formatIngredientLine(line, displayState = detailIngredientDisplayState) {
  const parsed = parseLeadingQuantity(line);
  if (!parsed) return line;

  const state = displayState || detailIngredientDisplayState;
  const baseServings = Number.isFinite(state.baseServings) && state.baseServings > 0 ? state.baseServings : 1;
  const targetServings = Number.isFinite(state.targetServings) && state.targetServings > 0 ? state.targetServings : baseServings;
  const convertMode = ["original", "metric", "imperial"].includes(state.convertMode) ? state.convertMode : "original";
  const ratio = targetServings / baseServings;
  if (convertMode === "original" && Math.abs(ratio - 1) < 0.000001) {
    return line;
  }
  const scaledQuantity = parsed.quantity * ratio;
  const unitInfo = parseLeadingUnit(parsed.remaining);
  const converted = convertQuantityAndUnit(scaledQuantity, unitInfo, convertMode);
  const quantityText = formatDisplayQuantity(
    converted.quantity,
    convertMode,
    converted.unit
  );
  if (!quantityText) return line;

  if (!unitInfo) {
    return `${quantityText} ${parsed.remaining}`.trim();
  }

  const nextUnitText = pluralizedUnit(converted.unit, converted.quantity);
  return `${quantityText} ${nextUnitText} ${unitInfo.rest}`.trim();
}

function getStoredMeasurementModes() {
  try {
    const parsed = JSON.parse(localStorage.getItem(MEASUREMENT_MODE_STORAGE_KEY) || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_error) {
    return {};
  }
}

function getRecipeMeasurementMode(recipe) {
  const recipeId = String(recipe?.id || "").trim();
  const modes = getStoredMeasurementModes();
  const mode = recipeId ? modes[recipeId] : modes.__last;
  return ["original", "metric", "imperial"].includes(mode) ? mode : "original";
}

function storeRecipeMeasurementMode(recipe, mode) {
  const normalizedMode = ["original", "metric", "imperial"].includes(mode) ? mode : "original";
  const recipeId = String(recipe?.id || "").trim();
  const modes = getStoredMeasurementModes();
  modes.__last = normalizedMode;
  if (recipeId) modes[recipeId] = normalizedMode;
  try {
    localStorage.setItem(MEASUREMENT_MODE_STORAGE_KEY, JSON.stringify(modes));
  } catch (_error) {
    // Display preference persistence is best-effort.
  }
}

function renderDetailIngredients(recipe) {
  if (!detailIngredientsEl) return;
  const ingredientGroups = sanitizeIngredientGroups(recipe?.ingredient_groups);
  const groupedMarkup = ingredientGroups
    .map((group) => {
      const groupTitle = String(group?.title || "").trim();
      const titleMarkup = groupTitle && !isGenericRecipeSectionTitle(groupTitle, "items")
        ? `<li class="detail-group-title"><strong>${escapeHtml(groupTitle)}</strong></li>`
        : "";
      const itemsMarkup = (Array.isArray(group?.items) ? group.items : [])
        .map((item) => `<li>${escapeHtml(formatIngredientLine(item))}</li>`)
        .join("");
      return `${titleMarkup}${itemsMarkup}`;
    })
    .join("");

  detailIngredientsEl.innerHTML = groupedMarkup || "<li class=\"detail-empty-item\">No ingredients available.</li>";
}

function setDetailConvertMode(nextMode) {
  detailIngredientDisplayState.convertMode = ["original", "metric", "imperial"].includes(nextMode) ? nextMode : "original";
  if (formState.selectedRecipe) {
    storeRecipeMeasurementMode(formState.selectedRecipe, detailIngredientDisplayState.convertMode);
  }
  if (detailConvertValueEl) {
    const labels = { original: "Original", metric: "Metric", imperial: "Imperial" };
    detailConvertValueEl.textContent = labels[detailIngredientDisplayState.convertMode];
  }
  if (detailConvertMenu) {
    detailConvertMenu.querySelectorAll("[data-convert-mode]").forEach((option) => {
      const selected = option.dataset.convertMode === detailIngredientDisplayState.convertMode;
      option.classList.toggle("is-selected", selected);
      option.setAttribute("aria-checked", selected ? "true" : "false");
    });
  }
}

function getFilteredRecipes(recipes) {
  const activeSearchInput = currentView === "cookbook" ? cookbookSearchInput : searchInput;
  const searchValue = (activeSearchInput?.value || "").trim().toLowerCase();

  return recipes.filter((recipe) => {
    if (!searchValue) return true;

    const normalizedTitle = String(recipe?.title || "").trim().toLowerCase();
    return normalizedTitle.includes(searchValue);
  });
}

function getVisibleCookbookRecipes() {
  if (!selectedCookbook) return [];
  const cookbookScoped = allRecipes.filter((recipe) => recipeBelongsToCookbook(recipe, selectedCookbook));
  return getFilteredRecipes(cookbookScoped);
}

function syncSelectedShoppingRecipeIds(visibleRecipes = getVisibleCookbookRecipes()) {
  if (!shoppingSelectionMode) return;
  const visibleRecipeIds = new Set(
    visibleRecipes.map((recipe) => String(recipe?.id || "").trim()).filter(Boolean)
  );

  selectedShoppingRecipeIds.forEach((recipeId) => {
    if (!visibleRecipeIds.has(recipeId)) {
      selectedShoppingRecipeIds.delete(recipeId);
    }
  });
}

function areAllVisibleRecipesSelected(visibleRecipes = getVisibleCookbookRecipes()) {
  if (!visibleRecipes.length) return false;
  return visibleRecipes.every((recipe) => selectedShoppingRecipeIds.has(String(recipe?.id || "").trim()));
}

function getRecipeCookbookNames(recipe) {
  const cookbooks = Array.isArray(recipe?.cookbooks) ? recipe.cookbooks : [];
  const isUncategorizedName = (name) => String(name || "").trim().toLowerCase() === "uncategorized";
  const names = cookbooks
    .map((entry) => String(entry?.name || "").trim())
    .filter((name) => Boolean(name) && !isUncategorizedName(name));
  if (names.length > 0) return names;
  return ["Uncategorized"];
}

function getRecipeCookbookIds(recipe) {
  const explicitIds = Array.isArray(recipe?.cookbook_ids) ? recipe.cookbook_ids : [];
  if (explicitIds.length) return explicitIds.map((id) => Number(id)).filter(Number.isFinite);
  const cookbooks = Array.isArray(recipe?.cookbooks) ? recipe.cookbooks : [];
  const isUncategorizedName = (name) => String(name || "").trim().toLowerCase() === "uncategorized";
  return cookbooks
    .filter((entry) => !isUncategorizedName(entry?.name))
    .map((entry) => Number(entry?.id))
    .filter(Number.isFinite);
}

function getCookbookName(recipe) {
  return getRecipeCookbookNames(recipe)[0] || "Uncategorized";
}

function recipeBelongsToCookbook(recipe, cookbookName) {
  const normalizedCookbookName = String(cookbookName || "").trim().toLowerCase();
  if (!normalizedCookbookName) return false;
  if (normalizedCookbookName === "uncategorized") {
    return getRecipeCookbookIds(recipe).length === 0;
  }
  return getRecipeCookbookNames(recipe).some((name) => name.toLowerCase() === normalizedCookbookName);
}

function getRecipesForCookbook(recipes, cookbookName) {
  return recipes.filter((recipe) => recipeBelongsToCookbook(recipe, cookbookName));
}

function buildCookbookGroups(recipes) {
  const cookbookMap = new Map();

  allCookbooks.forEach((cookbook) => {
    if (String(cookbook?.name || "").trim().toLowerCase() === "uncategorized") return;
    if (!cookbookMap.has(cookbook.name)) {
      cookbookMap.set(cookbook.name, {
        id: cookbook.id,
        name: cookbook.name,
        count: 0,
        images: [],
        cover_image: cookbook.cover_image || null
      });
    }
  });

  recipes.forEach((recipe) => {
    const cookbookNames = getRecipeCookbookNames(recipe);
    cookbookNames.forEach((cookbookName) => {
      if (String(cookbookName || "").trim().toLowerCase() === "uncategorized") return;
      if (!cookbookMap.has(cookbookName)) {
        cookbookMap.set(cookbookName, {
          name: cookbookName,
          count: 0,
          images: [],
          cover_image: null
        });
      }
    });
  });

  cookbookMap.forEach((group) => {
    const matchingRecipes = getRecipesForCookbook(recipes, group.name);
    group.count = matchingRecipes.length;
    group.images = matchingRecipes
      .map((recipe) => getRecipeImage(recipe))
      .filter(Boolean)
      .slice(0, 3);
  });

  const uncategorizedRecipes = getRecipesForCookbook(recipes, "Uncategorized");
  const uncategorizedCount = uncategorizedRecipes.length;
  if (uncategorizedCount > 0) {
    cookbookMap.set("Uncategorized", {
      id: null,
      name: "Uncategorized",
      count: uncategorizedCount,
      images: uncategorizedRecipes
        .map((recipe) => getRecipeImage(recipe))
        .filter(Boolean)
        .slice(0, 3),
      cover_image: null
    });
  }

  return Array.from(cookbookMap.values())
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
}

function getSelectedCookbookRecipeCount() {
  if (!selectedCookbook) return 0;
  return allRecipes.filter((recipe) => recipeBelongsToCookbook(recipe, selectedCookbook)).length;
}

function updateCookbookHeaderMeta() {
  if (!selectedCookbookCount) return;
  const recipeCount = getSelectedCookbookRecipeCount();
  const recipeLabel = recipeCount === 1 ? "recipe" : "recipes";
  selectedCookbookCount.textContent = `${recipeCount} ${recipeLabel}`;
}

function positionCookbookActionsMenu() {
  if (!cookbookActionsMenu || !cookbookMenuButton || !recipesListHeader) return;
  const headerBounds = recipesListHeader.getBoundingClientRect();
  const buttonBounds = cookbookMenuButton.getBoundingClientRect();
  const top = buttonBounds.bottom - headerBounds.top + 8;
  const left = buttonBounds.left - headerBounds.left;

  cookbookActionsMenu.style.setProperty("--menu-top", `${top}px`);
  cookbookActionsMenu.style.setProperty("--menu-left", `${left}px`);
}

function closeCookbookActionsMenu() {
  if (!cookbookActionsMenu || !cookbookMenuButton) return;
  cookbookActionsMenuOpen = false;
  cookbookActionsMenu.classList.add("hidden");
  cookbookMenuButton.setAttribute("aria-expanded", "false");
}

function openCookbookActionsMenu() {
  if (!cookbookActionsMenu || !cookbookMenuButton) return;
  cookbookActionsMenuOpen = true;
  positionCookbookActionsMenu();
  cookbookActionsMenu.classList.remove("hidden");
  cookbookMenuButton.setAttribute("aria-expanded", "true");
}

function toggleCookbookActionsMenu() {
  if (cookbookActionsMenuOpen) {
    closeCookbookActionsMenu();
    return;
  }
  openCookbookActionsMenu();
}

function closeDetailActionsMenu() {
  if (!detailActionsMenu || !detailMenuButton) return;
  detailActionsMenuOpen = false;
  detailActionsMenu.classList.add("hidden");
  detailMenuButton.setAttribute("aria-expanded", "false");
}

function openDetailActionsMenu() {
  if (!detailActionsMenu || !detailMenuButton) return;
  detailActionsMenuOpen = true;
  detailActionsMenu.classList.remove("hidden");
  detailMenuButton.setAttribute("aria-expanded", "true");
}

function toggleDetailActionsMenu() {
  if (detailActionsMenuOpen) {
    closeDetailActionsMenu();
    return;
  }
  openDetailActionsMenu();
}

function closeDetailConvertMenu() {
  if (!detailConvertMenu || !detailConvertButton) return;
  detailConvertMenuOpen = false;
  detailConvertMenu.classList.add("hidden");
  detailConvertButton.setAttribute("aria-expanded", "false");
}

function openDetailConvertMenu() {
  if (!detailConvertMenu || !detailConvertButton) return;
  detailConvertMenuOpen = true;
  detailConvertMenu.classList.remove("hidden");
  detailConvertButton.setAttribute("aria-expanded", "true");
}

function toggleDetailConvertMenu() {
  if (detailConvertMenuOpen) {
    closeDetailConvertMenu();
    return;
  }
  openDetailConvertMenu();
}

function toggleDetailCookbookPopover(force) {
  if (!detailCookbookPopover || !detailCookbookAddButton) return;
  detailCookbookPopoverOpen = typeof force === "boolean" ? force : !detailCookbookPopoverOpen;
  if (detailCookbookPopoverOpen && formState.selectedRecipe) {
    renderDetailCookbookMembership(formState.selectedRecipe);
  }
  detailCookbookPopover.classList.toggle("hidden", !detailCookbookPopoverOpen);
  detailCookbookAddButton.setAttribute("aria-expanded", detailCookbookPopoverOpen ? "true" : "false");
}

function normalizeTimeLabel(value) {
  if (value === null || value === undefined) return "";
  const raw = String(value).trim();
  return raw;
}

function updateRatingUi(rating) {
  if (!detailRatingStars) return;
  const normalizedRating = Math.max(0, Math.min(5, Number(rating) || 0));
  detailRatingStars.querySelectorAll("[data-rating-value]").forEach((star) => {
    const value = Number(star.dataset.ratingValue || "0");
    star.textContent = value <= normalizedRating ? "★" : "☆";
    star.classList.toggle("is-active", value <= normalizedRating);
    star.setAttribute("aria-checked", value === normalizedRating ? "true" : "false");
  });
}

function renderDetailCookbookMembership(recipe, preserveDraftSelection = false) {
  if (!detailCookbookMembership || !detailCookbookOptions) return;

  const selectedCookbookNames = getRecipeCookbookNames(recipe);
  const selectedCookbookIds = new Set(getRecipeCookbookIds(recipe).map((id) => String(id)));
  const isUncategorized = selectedCookbookIds.size === 0;
  detailCookbookMembership.innerHTML = selectedCookbookNames
    .map((name) => `<span class="detail-cookbook-pill">${escapeHtml(name)}</span>`)
    .join("");

  if (!preserveDraftSelection) {
    detailCookbookDraftSelection = isUncategorized
      ? new Set([UNCATEGORIZED_COOKBOOK_ID])
      : selectedCookbookIds;
  }

  const cookbookGroups = buildCookbookGroups(allRecipes);
  if (!cookbookGroups.some((group) => group.name.toLowerCase() === "uncategorized")) {
    cookbookGroups.push({ id: null, name: "Uncategorized", count: 0, images: [] });
  }

  detailCookbookOptions.innerHTML = cookbookGroups
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }))
    .map((group) => {
      const groupId = group.id === null || group.id === undefined ? UNCATEGORIZED_COOKBOOK_ID : String(group.id);
      const checked = detailCookbookDraftSelection.has(groupId);
      const thumbnail = group.images?.[0]
        ? `<img class="detail-cookbook-option-thumb" src="${escapeHtml(group.images[0])}" alt="" loading="lazy" aria-hidden="true" />`
        : `<span class="detail-cookbook-option-thumb-placeholder" aria-hidden="true">🍽</span>`;
      const recipeLabel = group.count === 1 ? "recipe" : "recipes";
      return `
        <label class="detail-cookbook-option">
          <span class="detail-cookbook-option-main">
            ${thumbnail}
            <span class="detail-cookbook-option-meta">
              <span class="detail-cookbook-option-title">${escapeHtml(group.name)}</span>
              <span class="detail-cookbook-option-count">${group.count} ${recipeLabel}</span>
            </span>
          </span>
          <input type="checkbox" name="detail-cookbook-choice" value="${escapeHtml(groupId)}" ${checked ? "checked" : ""} />
        </label>
      `;
    })
    .join("");
}

async function renameCurrentCookbook() {
  if (!selectedCookbook) return;

  const proposedName = window.prompt("Rename cookbook", selectedCookbook);
  const nextName = String(proposedName || "").trim();
  if (!nextName || nextName.toLowerCase() === selectedCookbook.toLowerCase()) return;

  const cookbook = allCookbooks.find((entry) => entry.name.toLowerCase() === selectedCookbook.toLowerCase());
  if (!cookbook?.id) {
    window.alert("Only saved cookbooks can be renamed.");
    return;
  }
  const existingNames = new Set(allCookbooks.map((group) => group.name.toLowerCase()));
  if (existingNames.has(nextName.toLowerCase())) {
    window.alert("A cookbook with that name already exists.");
    return;
  }

  await apiFetch(`${API_BASE}/cookbooks/${cookbook.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: nextName })
  });
  selectedCookbook = nextName;
  if (selectedCookbookTitle) selectedCookbookTitle.textContent = selectedCookbook;
  await loadRecipes();
}

async function deleteCurrentCookbook() {
  if (!selectedCookbook) return;

  const shouldDelete = window.confirm(
    `Delete cookbook "${selectedCookbook}"?\n\nRecipes will be moved to "Uncategorized".`
  );
  if (!shouldDelete) return;
  const cookbook = allCookbooks.find((entry) => entry.name.toLowerCase() === selectedCookbook.toLowerCase());
  if (!cookbook?.id) {
    window.alert("Only saved cookbooks can be deleted.");
    return;
  }
  await apiFetch(`${API_BASE}/cookbooks/${cookbook.id}`, { method: "DELETE" });
  navigateToDashboardHome();
  await loadRecipes();
}

function updateEmptyStateMessage(filteredCount) {
  if (!emptyState) return;
  if (allRecipes.length === 0) {
    emptyState.textContent = "No recipes yet. Add one with the Add Recipe button.";
    return;
  }

  if (filteredCount === 0) {
    emptyState.textContent = selectedCookbook
      ? `No recipes found in "${selectedCookbook}" for this search.`
      : "No recipes match your search.";
  }
}

function showAdminUsersStatus(message, isError = false) {
  if (!adminUsersStatus) return;
  adminUsersStatus.textContent = message || "";
  adminUsersStatus.classList.toggle("hidden", !message);
  adminUsersStatus.style.backgroundColor = isError ? "#fee2e2" : "#dcfce7";
  adminUsersStatus.style.color = isError ? "#991b1b" : "#166534";
}

function formatAdminDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function setDashboardView() {
  currentView = "dashboard";
  selectedCookbook = "";
  resetShoppingSelection();
  hideShoppingListView();
  closeCookbookActionsMenu();
  formState.selectedRecipe = null;
  currentDetailRecipeId = "";
  if (recipeDetailView) recipeDetailView.classList.add("hidden");
  if (dashboardMainPanel) dashboardMainPanel.classList.remove("hidden");
  if (cookbooksPanel) cookbooksPanel.classList.remove("hidden");
  if (cookbookView) cookbookView.classList.add("hidden");
  if (adminUsersPanel) adminUsersPanel.classList.add("hidden");
  if (settingsPanel) settingsPanel.classList.add("hidden");
  if (recipesContainer) recipesContainer.classList.remove("hidden");
  if (recipesListHeader) recipesListHeader.classList.remove("hidden");
  if (pageContainer) pageContainer.classList.remove("detail-mode");
  updateSidePanelActiveState();
}

function setAdminUsersView() {
  const isAdmin = userCanAccessAdminUsersView();
  if (!isAdmin) {
    navigateToDashboardHome();
    return;
  }

  currentView = "admin-users";
  selectedCookbook = "";
  resetShoppingSelection();
  hideShoppingListView();
  closeCookbookActionsMenu();
  formState.selectedRecipe = null;
  currentDetailRecipeId = "";
  if (recipeDetailView) recipeDetailView.classList.add("hidden");
  if (dashboardMainPanel) dashboardMainPanel.classList.add("hidden");
  if (cookbookView) cookbookView.classList.add("hidden");
  if (adminUsersPanel) adminUsersPanel.classList.remove("hidden");
  if (cookbooksPanel) cookbooksPanel.classList.add("hidden");
  if (dashboardSearchPanel) dashboardSearchPanel.classList.add("hidden");
  if (pageContainer) pageContainer.classList.remove("detail-mode");
  updateSidePanelActiveState();
}

async function refreshImportSettings() {
  const response = await apiFetch(`${API_BASE}/settings/import`);
  if (!response.ok) return;
  const payload = await response.json();
  const cookieStatus = String(
    payload.facebook_cookie_status || (payload.has_facebook_cookie ? "configured" : "missing")
  ).toLowerCase();
  if (facebookCookieState) {
    if (cookieStatus === "unreadable") {
      facebookCookieState.textContent = "Saved Facebook cookie needs to be reset.";
    } else {
      facebookCookieState.textContent = payload.has_facebook_cookie
        ? `Facebook cookie saved${payload.facebook_cookie_updated_at ? ` (updated ${new Date(payload.facebook_cookie_updated_at).toLocaleString()})` : ""}`
        : "No Facebook cookie saved";
    }
  }
  if (facebookCookieInput) facebookCookieInput.value = "";
  if (facebookCookieTestState) facebookCookieTestState.textContent = "";
  if (settingsStatus) {
    const warning = String(payload.facebook_cookie_warning || "").trim();
    settingsStatus.textContent = warning;
    settingsStatus.classList.toggle("hidden", !warning);
    settingsStatus.classList.remove("success", "info");
    settingsStatus.classList.toggle("error", Boolean(warning));
  }
  await refreshImportServicesStatus();
}

function formatServiceStatusLabel(statusValue) {
  const normalized = String(statusValue || "").toLowerCase();
  if (normalized === "online") return "Online";
  if (normalized === "offline") return "Offline";
  return "Not configured";
}

async function refreshImportServicesStatus() {
  if (!importServicesStatusList) return;
  importServicesStatusList.textContent = "Checking services...";
  try {
    const response = await apiFetch(`${API_BASE}/status/import-services`);
    if (!response.ok) {
      importServicesStatusList.textContent = "Could not load service status.";
      return;
    }
    const payload = await response.json();
    const services = payload?.services && typeof payload.services === "object" ? payload.services : {};
    const rows = Object.entries(services).map(([serviceKey, serviceValue]) => {
      const statusLabel = formatServiceStatusLabel(serviceValue?.status);
      const safeName = serviceKey.replaceAll("_", " ");
      const checkedAt = serviceValue?.last_checked_at ? new Date(serviceValue.last_checked_at).toLocaleString() : "—";
      const serviceUrl = String(serviceValue?.url || "").trim();
      return `${safeName}: ${statusLabel}${serviceUrl ? ` (${serviceUrl})` : ""} · checked ${checkedAt}`;
    });
    importServicesStatusList.innerHTML = rows.map((row) => `<div>${escapeHtml(row)}</div>`).join("");
    const warning = String(payload?.warning || "").trim();
    if (importServicesWarning) {
      importServicesWarning.textContent = warning;
      importServicesWarning.classList.toggle("hidden", !warning);
    }
  } catch (_error) {
    importServicesStatusList.textContent = "Could not load service status.";
  }
}

function setSettingsView() {
  currentView = "settings";
  if (dashboardMainPanel) dashboardMainPanel.classList.add("hidden");
  if (cookbookView) cookbookView.classList.add("hidden");
  if (adminUsersPanel) adminUsersPanel.classList.add("hidden");
  if (cookbooksPanel) cookbooksPanel.classList.add("hidden");
  if (settingsPanel) settingsPanel.classList.remove("hidden");
  updateSidePanelActiveState();
}

function setCookbookView(cookbookName) {
  currentView = "cookbook";
  selectedCookbook = cookbookName;
  resetShoppingSelection();
  hideShoppingListView();
  hideRecipeDetail(false);
  if (selectedCookbookTitle) selectedCookbookTitle.textContent = selectedCookbook || "Cookbook";
  updateCookbookHeaderMeta();
  closeCookbookActionsMenu();
  if (dashboardMainPanel) dashboardMainPanel.classList.add("hidden");
  if (cookbooksPanel) cookbooksPanel.classList.add("hidden");
  if (cookbookView) cookbookView.classList.remove("hidden");
  updateSidePanelActiveState();
}

function clearRecipeFilters() {
  if (searchInput) searchInput.value = "";
  if (cookbookSearchInput) cookbookSearchInput.value = "";
}

function navigateToDashboardHome() {
  setDashboardView();
  clearRecipeFilters();
  applyRecipeFilters();
}

function openRecipe(recipe) {
  if (!recipe) return;
  if (currentView !== "cookbook") {
    setCookbookView(getCookbookName(recipe));
    applyRecipeFilters();
  }
  showRecipeDetail(recipe);
}

function getDetailRecipeSelection() {
  if (formState.selectedRecipe?.id) return formState.selectedRecipe;
  const fallbackRecipeId = String(currentDetailRecipeId || "").trim();
  if (!fallbackRecipeId) return null;
  return allRecipes.find((recipe) => String(recipe.id) === fallbackRecipeId) || null;
}

function stopReviewStatusPolling() {
  if (!reviewStatusPollTimer) return;
  window.clearInterval(reviewStatusPollTimer);
  reviewStatusPollTimer = null;
}

function startReviewStatusPolling(recipeId) {
  stopReviewStatusPolling();
  const normalizedRecipeId = String(recipeId || "").trim();
  if (!normalizedRecipeId) return;
  reviewStatusPollTimer = window.setInterval(async () => {
    const selectedId = String(formState.selectedRecipe?.id || "").trim();
    if (!selectedId || selectedId !== normalizedRecipeId) {
      stopReviewStatusPolling();
      return;
    }
    const response = await apiFetch(`${API_BASE}/recipes/${normalizedRecipeId}/review-status`);
    if (!response.ok) return;
    const statusPayload = await response.json();
    const nextStatus = String(statusPayload.review_status || "").toLowerCase();
    updateRecipeInMemory(normalizedRecipeId, statusPayload);
    if (formState.selectedRecipe && String(formState.selectedRecipe.id) === normalizedRecipeId) {
      formState.selectedRecipe = { ...formState.selectedRecipe, ...statusPayload };
      if (detailReviewStatusEl) {
        const statusLabel = {
          queued: "Queued for AI review",
          processing: "Processing...",
          failed: "AI review failed"
        }[nextStatus] || "";
        detailReviewStatusEl.textContent = statusLabel;
        detailReviewStatusEl.classList.toggle("hidden", !statusLabel);
      }
    }
    if (nextStatus === "completed" || nextStatus === "failed") {
      stopReviewStatusPolling();
      await loadRecipes();
      const refreshed = allRecipes.find((item) => String(item.id) === normalizedRecipeId);
      if (refreshed) showRecipeDetail(refreshed);
    }
  }, REVIEW_STATUS_POLL_INTERVAL_MS);
}

function applyRecipeFilters() {
  const normalizedSearch = (searchInput?.value || "").trim().toLowerCase();
  const dashboardSearchActive = currentView === "dashboard" && Boolean(normalizedSearch);
  const dashboardSearchMatches = dashboardSearchActive
    ? allRecipes.filter((recipe) => (recipe.title || "").toLowerCase().includes(normalizedSearch))
    : [];
  const cookbookScoped = selectedCookbook
    ? allRecipes.filter((recipe) => recipeBelongsToCookbook(recipe, selectedCookbook))
    : [];
  const baseFiltered = getFilteredRecipes(cookbookScoped);
  syncSelectedShoppingRecipeIds(baseFiltered);

  renderRecipes(baseFiltered);
  renderRecipes(dashboardSearchMatches, dashboardSearchResults);
  updateEmptyStateMessage(baseFiltered.length);
  if (emptyState) {
    emptyState.classList.toggle("hidden", baseFiltered.length > 0);
  }
  if (dashboardSearchEmptyState) {
    dashboardSearchEmptyState.classList.toggle("hidden", dashboardSearchMatches.length > 0);
  }

  const allCookbooks = buildCookbookGroups(allRecipes);
  if (selectedCookbook && !allCookbooks.some((group) => group.name === selectedCookbook)) {
    selectedCookbook = "";
  }
  updateCookbookHeaderMeta();
  renderCookbooks(allCookbooks);
  renderSideCookbooks(allCookbooks);
  updateCookbookView();
  updateShoppingSelectionControls();
}

function updateSidePanelActiveState() {
  if (navCookbooksButton) {
    const dashboardActive = currentView === "dashboard";
    navCookbooksButton.classList.toggle("is-active", dashboardActive);
    navCookbooksButton.setAttribute("aria-current", dashboardActive ? "page" : "false");
  }
  if (navGroceriesButton) {
    const groceryViewActive = currentView === "grocery";
    navGroceriesButton.classList.toggle("is-active", groceryViewActive);
    navGroceriesButton.setAttribute("aria-current", groceryViewActive ? "page" : "false");
  }
  if (navMealPlanButton) {
    const mealPlanViewActive = currentView === "meal-plan";
    navMealPlanButton.classList.toggle("is-active", mealPlanViewActive);
    navMealPlanButton.setAttribute("aria-current", mealPlanViewActive ? "page" : "false");
  }
  if (navAdminUsersButton) {
    const adminViewActive = currentView === "admin-users";
    navAdminUsersButton.classList.toggle("is-active", adminViewActive);
    navAdminUsersButton.setAttribute("aria-current", adminViewActive ? "page" : "false");
  }
  if (navSettingsButton) {
    const settingsActive = currentView === "settings";
    navSettingsButton.classList.toggle("is-active", settingsActive);
    navSettingsButton.setAttribute("aria-current", settingsActive ? "page" : "false");
  }
  if (mobileNavRecipesButton) {
    const dashboardActive = currentView === "dashboard";
    mobileNavRecipesButton.classList.toggle("is-active", dashboardActive);
    mobileNavRecipesButton.setAttribute("aria-current", dashboardActive ? "page" : "false");
  }
  if (mobileNavGroceriesButton) {
    const groceryViewActive = currentView === "grocery";
    mobileNavGroceriesButton.classList.toggle("is-active", groceryViewActive);
    mobileNavGroceriesButton.setAttribute("aria-current", groceryViewActive ? "page" : "false");
  }
  if (mobileNavMealPlanButton) {
    const mealPlanViewActive = currentView === "meal-plan";
    mobileNavMealPlanButton.classList.toggle("is-active", mealPlanViewActive);
    mobileNavMealPlanButton.setAttribute("aria-current", mealPlanViewActive ? "page" : "false");
  }
}

function renderSideCookbooks(cookbooks) {
  if (!sideCookbookList) return;

  sideCookbookList.innerHTML = cookbooks
    .map((cookbook) => {
      const safeName = escapeHtml(cookbook.name);
      const encodedName = encodeURIComponent(cookbook.name);
      const isActive = currentView === "cookbook" && selectedCookbook === cookbook.name;
      const thumbnail = cookbook.images?.[0]
        ? `<img class="side-cookbook-thumb" src="${escapeHtml(cookbook.images[0])}" alt="" loading="lazy" aria-hidden="true" />`
        : `<span class="side-cookbook-thumb-placeholder" aria-hidden="true">🍽</span>`;
      const recipeLabel = cookbook.count === 1 ? "recipe" : "recipes";
      return `
        <button type="button" class="side-cookbook-item${isActive ? " is-active" : ""}" data-side-cookbook="${encodedName}" aria-label="Open ${safeName}" ${isActive ? "aria-current=\"page\"" : ""}>
          ${thumbnail}
          <span class="side-cookbook-meta">
            <span class="side-cookbook-name" title="${safeName}">${safeName}</span>
            <span class="side-cookbook-count">${cookbook.count} ${recipeLabel}</span>
          </span>
        </button>
      `;
    })
    .join("");

  sideCookbookList.querySelectorAll("[data-side-cookbook]").forEach((button) => {
    button.addEventListener("click", () => {
      const cookbookName = decodeURIComponent(button.dataset.sideCookbook || "");
      setCookbookView(cookbookName);
      if (searchInput) searchInput.value = "";
      if (cookbookSearchInput) cookbookSearchInput.value = "";
      applyRecipeFilters();
    });
  });

  updateSidePanelActiveState();
}

function updateCookbookView() {
  const inCookbookView = currentView === "cookbook" && Boolean(selectedCookbook);
  const inGroceryView = currentView === "grocery";
  const inMealPlanView = currentView === "meal-plan";
  const dashboardSearchActive = currentView === "dashboard" && Boolean((searchInput?.value || "").trim());

  if (cookbookView) cookbookView.classList.toggle("hidden", !inCookbookView && !inGroceryView);
  if (mealPlanView) mealPlanView.classList.toggle("hidden", !inMealPlanView);
  if (selectedCookbookTitle) {
    selectedCookbookTitle.textContent = selectedCookbook || "Cookbook";
  }
  if (backToCookbooksButton) {
    backToCookbooksButton.classList.toggle("hidden", false);
  }
  if (dashboardMainPanel) dashboardMainPanel.classList.toggle("hidden", inCookbookView || inGroceryView || inMealPlanView);
  if (cookbooksPanel) cookbooksPanel.classList.toggle("hidden", inCookbookView || inGroceryView || inMealPlanView || dashboardSearchActive);
  if (dashboardSearchPanel) dashboardSearchPanel.classList.toggle("hidden", inCookbookView || inGroceryView || inMealPlanView || !dashboardSearchActive);
  if (inGroceryView) {
    if (recipesContainer) recipesContainer.classList.add("hidden");
    if (recipesListHeader) recipesListHeader.classList.add("hidden");
    if (shoppingListView) shoppingListView.classList.remove("hidden");
  } else if (inCookbookView && recipeDetailView && recipeDetailView.classList.contains("hidden")) {
    if (recipesContainer) recipesContainer.classList.remove("hidden");
    if (recipesListHeader) recipesListHeader.classList.remove("hidden");
  }
}

function syncAdminSecurityForm() {
  if (authLockoutEnabledInput) {
    authLockoutEnabledInput.checked = Boolean(adminSecuritySettings.auth_lockout_enabled);
  }
  if (authMaxFailedAttemptsInput) {
    authMaxFailedAttemptsInput.value = String(adminSecuritySettings.auth_max_failed_attempts || 5);
  }
  if (authLockoutMinutesInput) {
    authLockoutMinutesInput.value = String(adminSecuritySettings.auth_lockout_minutes ?? 15);
  }
}

async function refreshAdminSecuritySettings() {
  if (!currentUser?.is_admin) return;
  const response = await apiFetch(`${API_BASE}/admin/security-settings`);
  if (!response.ok) {
    showAdminUsersStatus("Failed to load security settings.", true);
    return;
  }
  const payload = await response.json();
  adminSecuritySettings = {
    auth_lockout_enabled: Boolean(payload?.auth_lockout_enabled),
    auth_max_failed_attempts: Math.max(1, Number(payload?.auth_max_failed_attempts || 5)),
    auth_lockout_minutes: Math.max(0, Number(payload?.auth_lockout_minutes ?? 15))
  };
  syncAdminSecurityForm();
}

async function refreshAdminUsers() {
  if (!currentUser?.is_admin) return;
  const response = await apiFetch(`${API_BASE}/admin/users`);
  if (!response.ok) {
    showAdminUsersStatus("Failed to load users.", true);
    return;
  }
  adminUsers = await response.json();
  renderAdminUsersTable();
}

async function runAdminAction(url, options, successMessage) {
  const response = await apiFetch(url, options);
  if (!response.ok) {
    let detail = "Request failed.";
    try {
      const errorJson = await response.json();
      if (errorJson?.detail) detail = errorJson.detail;
    } catch (_) {}
    showAdminUsersStatus(detail, true);
    return false;
  }
  showAdminUsersStatus(successMessage, false);
  await refreshAdminUsers();
  return true;
}

function renderAdminUsersTable() {
  if (!adminUsersTableWrap) return;
  if (!adminUsers.length) {
    adminUsersTableWrap.innerHTML = `<p class="admin-users-empty">No users found.</p>`;
    return;
  }
  const rows = adminUsers
    .map((user) => {
      const isSelf = Number(user.id) === Number(currentUser?.id);
      const activeLabel = user.is_active ? "Active" : "Inactive";
      const roleLabel = user.is_admin ? "Admin" : "User";
      const lockLabel = user.is_locked_manual ? "Manual lock" : "No manual lock";
      const timedLockLabel = user.locked_until ? formatAdminDate(user.locked_until) : "—";
      const failedAttemptsLabel = Number(user.failed_login_attempts || 0);
      const lockActionLabel = user.is_locked_manual ? "Unlock" : "Lock";
      return `
        <tr>
          <td class="admin-user-cell">
            <div class="admin-user-email">${escapeHtml(user.email || "")}</div>
            <div class="admin-user-display">${escapeHtml(user.display_name || "—")}</div>
          </td>
          <td>
            <div class="admin-badge-row">
              <span class="admin-badge admin-badge-role">${roleLabel}</span>
              <span class="admin-badge ${user.is_active ? "admin-badge-success" : "admin-badge-muted"}">${activeLabel}</span>
              <span class="admin-badge ${user.is_locked_manual ? "admin-badge-warn" : "admin-badge-muted"}">${lockLabel}</span>
            </div>
          </td>
          <td class="admin-mono-cell">
            <div>${timedLockLabel}</div>
            <div class="admin-subtle-text">${failedAttemptsLabel} failed attempts</div>
          </td>
          <td class="admin-mono-cell">
            <div>${formatAdminDate(user.created_at)}</div>
            <div class="admin-subtle-text">Last login: ${formatAdminDate(user.last_login)}</div>
          </td>
          <td>
            <div class="admin-inline-edit">
              <input type="text" value="${escapeHtml(user.display_name || "")}" data-admin-display-name="${user.id}" placeholder="Display name" />
              <label><input type="checkbox" data-admin-role="${user.id}" ${user.is_admin ? "checked" : ""} ${isSelf ? "disabled" : ""} /> <span>Admin</span></label>
              <button type="button" class="admin-button admin-button-primary admin-button-compact" data-admin-save="${user.id}">Save</button>
            </div>
          </td>
          <td>
            <div class="admin-users-actions">
              <button type="button" class="admin-button admin-button-secondary admin-button-compact" data-admin-reset="${user.id}">Reset password</button>
              <button type="button" class="admin-button admin-button-secondary admin-button-compact" data-admin-toggle-lock="${user.id}" ${isSelf ? "disabled" : ""}>${lockActionLabel}</button>
              <button type="button" class="admin-button ${user.is_active ? "admin-button-danger" : "admin-button-secondary"} admin-button-compact" data-admin-toggle-active="${user.id}" ${isSelf ? "disabled" : ""}>${user.is_active ? "Deactivate" : "Activate"}</button>
              <button type="button" class="admin-button admin-button-danger admin-button-compact" data-admin-delete="${user.id}" ${isSelf ? "disabled" : ""}>Delete</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
  adminUsersTableWrap.innerHTML = `
    <table class="admin-users-table">
      <thead>
        <tr>
          <th>User</th>
          <th>Access</th>
          <th>Lockout</th>
          <th>Activity</th>
          <th>Edit</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  adminUsersTableWrap.querySelectorAll("[data-admin-save]").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = Number(button.dataset.adminSave);
      const nameInput = adminUsersTableWrap.querySelector(`[data-admin-display-name="${userId}"]`);
      const roleInput = adminUsersTableWrap.querySelector(`[data-admin-role="${userId}"]`);
      await runAdminAction(
        `${API_BASE}/admin/users/${userId}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            display_name: nameInput?.value || "",
            is_admin: Boolean(roleInput?.checked)
          })
        },
        "User updated."
      );
    });
  });

  adminUsersTableWrap.querySelectorAll("[data-admin-reset]").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = Number(button.dataset.adminReset);
      const password = window.prompt("Set a new temporary password:");
      if (!password) return;
      await runAdminAction(
        `${API_BASE}/admin/users/${userId}/reset-password`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password })
        },
        "Password reset and sessions cleared."
      );
    });
  });

  adminUsersTableWrap.querySelectorAll("[data-admin-toggle-active]").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = Number(button.dataset.adminToggleActive);
      const user = adminUsers.find((entry) => Number(entry.id) === userId);
      const endpoint = user?.is_active ? "deactivate" : "activate";
      await runAdminAction(
        `${API_BASE}/admin/users/${userId}/${endpoint}`,
        { method: "POST" },
        user?.is_active ? "User deactivated." : "User activated."
      );
    });
  });

  adminUsersTableWrap.querySelectorAll("[data-admin-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = Number(button.dataset.adminDelete);
      const target = adminUsers.find((entry) => Number(entry.id) === userId);
      const confirmed = window.confirm(`Delete user ${target?.email || userId}?`);
      if (!confirmed) return;
      await runAdminAction(
        `${API_BASE}/admin/users/${userId}`,
        { method: "DELETE" },
        "User deleted."
      );
    });
  });

  adminUsersTableWrap.querySelectorAll("[data-admin-toggle-lock]").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = Number(button.dataset.adminToggleLock);
      const user = adminUsers.find((entry) => Number(entry.id) === userId);
      const endpoint = user?.is_locked_manual ? "unlock" : "lock";
      await runAdminAction(
        `${API_BASE}/admin/users/${userId}/${endpoint}`,
        { method: "POST" },
        user?.is_locked_manual ? "User unlocked." : "User locked."
      );
    });
  });
}

function renderCookbooks(cookbooks) {
  if (!cookbookGrid) return;

  const cookbookTilesMarkup = cookbooks
    .map((cookbook) => {
      const safeName = escapeHtml(cookbook.name);
      const recipeLabel = cookbook.count === 1 ? "recipe" : "recipes";
      const tilePreviewImage = String(cookbook.cover_image || cookbook.images?.[0] || "").trim();
      const mediaMarkup = tilePreviewImage
        ? `<img class="cookbook-tile-image cookbook-tile-image-single" src="${escapeHtml(tilePreviewImage)}" alt="${safeName} cookbook image" loading="lazy" />`
        : `<div class="cookbook-tile-placeholder" aria-hidden="true"><span class="cookbook-tile-placeholder-icon">🍽</span></div>`;

      return `
        <button type="button" class="cookbook-tile${selectedCookbook === cookbook.name ? " is-active" : ""}" data-cookbook-name="${safeName}" aria-label="Open ${safeName} cookbook">
          <div class="cookbook-tile-media">
            ${mediaMarkup}
            <span class="card-media-overlay" aria-hidden="true"></span>
          </div>
          <div class="cookbook-tile-content">
            <h4 class="cookbook-tile-title" title="${safeName}">${safeName}</h4>
            <p class="cookbook-tile-count">${cookbook.count} ${recipeLabel}</p>
          </div>
        </button>
      `;
    })
    .join("");

  const newCookbookTileMarkup = `
    <button type="button" class="cookbook-tile cookbook-tile-new" data-new-cookbook="true" aria-label="Create a new cookbook">
      <div class="cookbook-tile-media cookbook-tile-media-new" aria-hidden="true">
        <span class="cookbook-tile-plus">＋</span>
      </div>
      <div class="cookbook-tile-content">
        <h4 class="cookbook-tile-title">New cookbook</h4>
        <p class="cookbook-tile-count">Create a collection</p>
      </div>
    </button>
  `;

  cookbookGrid.innerHTML = `${newCookbookTileMarkup}${cookbookTilesMarkup}`;

  cookbookGrid.querySelectorAll("[data-cookbook-name]").forEach((tile) => {
    tile.addEventListener("click", () => {
      const clickedCookbook = tile.dataset.cookbookName || "";
      setCookbookView(clickedCookbook);
      if (searchInput) searchInput.value = "";
      if (cookbookSearchInput) cookbookSearchInput.value = "";
      applyRecipeFilters();
    });
  });

  cookbookGrid.querySelectorAll("[data-new-cookbook]").forEach((tile) => {
    tile.addEventListener("click", async () => {
      const name = window.prompt("Cookbook name?");
      const trimmedName = String(name || "").trim();
      if (!trimmedName) return;

      const existingNames = new Set(allCookbooks.map((group) => group.name.toLowerCase()));
      if (!existingNames.has(trimmedName.toLowerCase())) {
        await apiFetch(`${API_BASE}/cookbooks`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: trimmedName })
        });
      }
      await loadRecipes();
      setCookbookView(trimmedName);
      if (searchInput) searchInput.value = "";
      if (cookbookSearchInput) cookbookSearchInput.value = "";
      applyRecipeFilters();
    });
  });
}

function showStatus(message) {
  if (!statusMessage) return;
  statusMessage.textContent = message;
  statusMessage.classList.remove("hidden");
}

function clearAddRecipeStatus() {
  if (!addRecipeStatus) return;
  addRecipeStatus.textContent = "";
  addRecipeStatus.classList.remove("success", "info");
  addRecipeStatus.classList.add("error");
  addRecipeStatus.classList.add("hidden");
}

function stopImportProgress() {
  if (!importProgressTimer) return;
  window.clearTimeout(importProgressTimer);
  importProgressTimer = null;
}

function startImportProgress(stages = [], delayMs = 1300) {
  stopImportProgress();
  const queue = Array.isArray(stages) ? stages.filter(Boolean) : [];
  if (!queue.length) return;
  let index = 0;
  showAddRecipeStatus(queue[index], "info");
  const tick = () => {
    index += 1;
    if (index >= queue.length) return;
    showAddRecipeStatus(queue[index], "info");
    importProgressTimer = window.setTimeout(tick, delayMs);
  };
  importProgressTimer = window.setTimeout(tick, delayMs);
}

function showAddRecipeStatus(message, tone = "error") {
  if (!addRecipeStatus) return;
  addRecipeStatus.textContent = message;
  addRecipeStatus.classList.toggle("success", tone === "success");
  addRecipeStatus.classList.toggle("info", tone === "info");
  addRecipeStatus.classList.toggle("error", tone !== "success" && tone !== "info");
  addRecipeStatus.classList.remove("hidden");
}

function clearSocialResolutionDebug() {
  if (!socialResolutionDebug) return;
  socialResolutionDebug.classList.add("hidden");
  if (socialDebugOriginalUrl) socialDebugOriginalUrl.textContent = "";
  if (socialDebugCanonicalUrl) socialDebugCanonicalUrl.textContent = "";
  if (socialDebugPostId) socialDebugPostId.textContent = "";
  if (socialDebugMethod) socialDebugMethod.textContent = "";
  if (socialDebugResolvedUrl) socialDebugResolvedUrl.textContent = "";
}

function renderSocialResolutionDebug({ originalUrl = "", socialMetadata = null, resolvedUrl = "" } = {}) {
  if (!socialResolutionDebug) return;
  if (!socialMetadata || typeof socialMetadata !== "object") {
    clearSocialResolutionDebug();
    return;
  }

  if (socialDebugOriginalUrl) socialDebugOriginalUrl.textContent = String(originalUrl || "—");
  if (socialDebugCanonicalUrl) {
    socialDebugCanonicalUrl.textContent = String(socialMetadata.canonical_url || "—");
  }
  if (socialDebugPostId) socialDebugPostId.textContent = String(socialMetadata.post_id || "—");
  if (socialDebugMethod) socialDebugMethod.textContent = String(socialMetadata.method || "—");
  if (socialDebugResolvedUrl) socialDebugResolvedUrl.textContent = String(resolvedUrl || "—");
  socialResolutionDebug.classList.remove("hidden");
}

function sanitizeIngredientGroups(groups) {
  if (!Array.isArray(groups)) return [];

  return groups.map((group) => {
    const items = Array.isArray(group?.items)
      ? group.items.map((item) => normalizeAiCleanupIngredientValue(item)).filter(Boolean)
      : [];

    return {
      title: String(group?.title || "").trim(),
      items
    };
  });
}

function sanitizeInstructionGroups(groups) {
  if (Array.isArray(groups) && groups.length) {
    const cleaned = groups
      .map((group) => {
        const steps = Array.isArray(group?.steps)
          ? group.steps.map((item) => String(item || "").trim()).filter(Boolean)
          : [];
        const title = String(group?.title || "").trim();
        return { title, steps };
      })
      .filter((group) => group.steps.length);
    if (cleaned.length) return cleaned;
  }
  return [];
}

function isGenericRecipeSectionTitle(title, type) {
  const normalizedTitle = String(title || "")
    .replace(/\s+/g, " ")
    .replace(/:+\s*$/, "")
    .trim()
    .toLowerCase();
  if (!normalizedTitle) return false;

  const genericTitlesByType = {
    steps: new Set(["instructions", "instruction", "directions", "steps", "method"]),
    items: new Set(["ingredients", "ingredient"])
  };
  return genericTitlesByType[type]?.has(normalizedTitle) || false;
}

function renderGroupedList(groups, itemKey) {
  if (!Array.isArray(groups) || !groups.length) return "";
  const isInstructionList = itemKey === "steps";
  const formatInstructionTitle = (rawTitle) => {
    const cleaned = String(rawTitle || "")
      .replace(/\s+/g, " ")
      .replace(/:+\s*$/, "")
      .trim();
    if (!cleaned) return "";
    return cleaned
      .toLowerCase()
      .replace(/\b([a-z])/g, (match, letter) => letter.toUpperCase());
  };
  return groups
    .map((group) => {
      const title = isInstructionList
        ? formatInstructionTitle(group?.title)
        : String(group?.title || "").trim();
      const entries = Array.isArray(group?.[itemKey]) ? group[itemKey] : [];
      const itemsMarkup = entries
        .map((entry) => {
          const entryClass = isInstructionList ? " class=\"detail-instruction-step\"" : "";
          return `<li${entryClass}>${escapeHtml(entry)}</li>`;
        })
        .join("");
      if (!itemsMarkup) return "";
      const shouldRenderTitle = title && !isGenericRecipeSectionTitle(title, itemKey);
      const titleMarkup = shouldRenderTitle
        ? `<li class="${isInstructionList ? "detail-instruction-group-title" : "detail-group-title"}">${escapeHtml(title)}</li>`
        : "";
      return `${titleMarkup}${itemsMarkup}`;
    })
    .join("");
}

function renderModalIngredientPreview(groups, fallbackIngredients = []) {
  const groupedPreview = Array.isArray(groups) ? groups : [];
  if (groupedPreview.length) {
    return groupedPreview
      .map((group) => {
        const groupTitle = String(group?.title || "").trim();
        let items = Array.isArray(group?.items)
          ? group.items.map((item) => String(item || "").trim()).filter(Boolean)
          : [];
        items = items.filter((item) => {
          const text = item.toLowerCase().trim();

          // remove obvious junk
          if (!text) return false;
          if (text.length > 120) return false;

          if (
            text.includes("prep time") ||
            text.includes("cook time") ||
            text.includes("total time") ||
            text.includes("video") ||
            text.includes("votes") ||
            text.includes("servings") ||
            text.includes("course") ||
            text.includes("cuisine") ||
            text.includes("ingredients") ||
            text.includes("instructions")
          ) return false;

          // remove lines that look like metadata blobs
          const junkPattern = /(servings|prep|cook|mins|min|course|cuisine)/i;
          if (junkPattern.test(text) && text.split(" ").length > 8) return false;

          return true;
        });
        if (!items.length) {
          return groupTitle
            ? `<div class="parsed-preview-group"><div class="parsed-preview-group-title">${escapeHtml(groupTitle)}</div></div>`
            : "";
        }
        const titleMarkup = groupTitle
          ? `<div class="parsed-preview-group-title">${escapeHtml(groupTitle)}</div>`
          : "";
        const itemsMarkup = items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
        return `<div class="parsed-preview-group">${titleMarkup}<ul>${itemsMarkup}</ul></div>`;
      })
      .filter(Boolean)
      .join("");
  }

  const fallback = Array.isArray(fallbackIngredients)
    ? fallbackIngredients.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  return fallback.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function renderModalInstructionPreview(groups, fallbackInstructions = []) {
  const groupedPreview = Array.isArray(groups) ? groups : [];
  if (groupedPreview.length) {
    return groupedPreview
      .map((group) => {
        const groupTitle = String(group?.title || "").trim();
        const steps = Array.isArray(group?.steps)
          ? group.steps.map((step) => String(step || "").trim()).filter(Boolean)
          : [];
        if (!steps.length) return "";
        const titleMarkup = groupTitle
          ? `<div class="parsed-preview-group-title">${escapeHtml(groupTitle)}</div>`
          : "";
        const stepsMarkup = steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("");
        return `<div class="parsed-preview-group">${titleMarkup}<ol>${stepsMarkup}</ol></div>`;
      })
      .filter(Boolean)
      .join("");
  }

  const fallback = Array.isArray(fallbackInstructions)
    ? fallbackInstructions.map((step) => String(step || "").trim()).filter(Boolean)
    : [];
  return fallback.map((step) => `<li>${escapeHtml(step)}</li>`).join("");
}

function normalizeEditableList(values) {
  return Array.isArray(values)
    ? values.map((item) => String(item ?? ""))
    : [];
}

function getEditableIngredients() {
  const groups = Array.isArray(formState.parsed.ingredient_groups)
    ? formState.parsed.ingredient_groups
    : [];
  if (groups.length) {
    const values = groups.flatMap((group) => {
      const title = String(group?.title || "").trim();
      const items = Array.isArray(group?.items) ? group.items.map((item) => String(item ?? "")) : [];
      return title ? [`# ${title}`, ...items] : items;
    });
    if (values.length) return values;
  }
  return normalizeEditableList(formState.parsed.ingredients);
}

function getEditableInstructions() {
  const groups = Array.isArray(formState.parsed.instruction_groups)
    ? formState.parsed.instruction_groups
    : [];
  if (groups.length) {
    const values = groups.flatMap((group) => {
      const title = String(group?.title || "").trim();
      const steps = Array.isArray(group?.steps) ? group.steps.map((step) => String(step ?? "")) : [];
      const isGenericInstructionTitle = title.toLowerCase() === "instructions";
      return title && !isGenericInstructionTitle ? [`# ${title}`, ...steps] : steps;
    });
    if (values.length) return values;
  }
  return normalizeEditableList(formState.parsed.instructions);
}

function syncParsedCollectionsFromEditable(ingredients, instructions) {
  if (Array.isArray(ingredients)) {
    const normalizedIngredients = normalizeEditableList(ingredients);
    const ingredientGroups = editableIngredientsToGroups(normalizedIngredients);
    formState.parsed.ingredients = ingredientGroups.flatMap((group) => group.items);
    formState.parsed.ingredient_groups = ingredientGroups.length
      ? ingredientGroups
      : [];
  }
  if (Array.isArray(instructions)) {
    const normalizedInstructions = normalizeEditableList(instructions);
    const instructionGroups = editableInstructionsToGroups(normalizedInstructions);
    formState.parsed.instructions = instructionGroups.flatMap((group) => group.steps);
    formState.parsed.instruction_groups = instructionGroups.length
      ? instructionGroups
      : [];
  }
}

function editableIngredientsToGroups(values) {
  const groups = [];
  let currentGroup = { title: "", items: [] };
  values.forEach((value) => {
    const text = String(value || "").trim();
    const bracketTitle = text.match(/^\[(.+)\]$/);
    const hashTitle = text.match(/^#\s*(.+)$/);
    const title = (hashTitle?.[1] || bracketTitle?.[1] || "").trim();
    if (title) {
      if (currentGroup.items.length || currentGroup.title) groups.push(currentGroup);
      currentGroup = { title, items: [] };
      return;
    }
    currentGroup.items.push(String(value ?? ""));
  });
  if (currentGroup.items.length || currentGroup.title) groups.push(currentGroup);
  return groups.filter((group) => group.title || group.items.length);
}

function editableInstructionsToGroups(values) {
  const groups = [];
  let currentGroup = { title: "", steps: [] };
  values.forEach((value) => {
    const text = String(value || "").trim();
    const bracketTitle = text.match(/^\[(.+)\]$/);
    const hashTitle = text.match(/^#\s*(.+)$/);
    const title = (hashTitle?.[1] || bracketTitle?.[1] || "").trim();
    if (title) {
      if (currentGroup.steps.length || currentGroup.title) groups.push(currentGroup);
      currentGroup = { title, steps: [] };
      return;
    }
    currentGroup.steps.push(String(value ?? ""));
  });
  if (currentGroup.steps.length || currentGroup.title) groups.push(currentGroup);
  return groups.filter((group) => group.title || group.steps.length);
}

function moveListItem(list, fromIndex, toIndex) {
  if (!Array.isArray(list)) return list;
  if (toIndex < 0 || toIndex >= list.length || fromIndex < 0 || fromIndex >= list.length) return list;
  const nextList = [...list];
  const [moved] = nextList.splice(fromIndex, 1);
  nextList.splice(toIndex, 0, moved);
  return nextList;
}

function renderEditableList(containerEl, values, options = {}) {
  if (!containerEl) return;
  const {
    type = "ingredient",
    reorderMode = false
  } = options;

  if (!values.length) {
    const label = type === "instruction" ? "instructions" : "ingredients";
    containerEl.innerHTML = `<p class="add-recipe-helper-text">No ${label} yet. Use the add link below to start.</p>`;
    return;
  }

  const rows = values
    .map((value, index) => {
      const textValue = String(value ?? "");
      const isSection = /^#\s*\S/.test(textValue);
      const displayValue = isSection ? textValue.replace(/^#\s*/, "") : textValue;
      const sectionAttr = isSection ? `data-${type}-section="true"` : "";
      const placeholder = isSection
        ? "Section name"
        : (type === "instruction" ? "Add an instruction step" : "Add an ingredient");
      return `
      <div class="parsed-edit-row ${isSection ? "parsed-edit-row-section" : ""}" data-${type}-row="${index}" data-testid="parsed-${type}-row">
        ${type === "instruction"
          ? `<textarea class="${isSection ? "parsed-section-input" : ""}" data-${type}-input="${index}" ${sectionAttr} rows="${isSection ? "1" : "2"}" placeholder="${placeholder}" aria-label="${isSection ? "instruction section" : `${type} ${index + 1}`}">${escapeHtml(displayValue)}</textarea>`
          : `<input type="text" class="${isSection ? "parsed-section-input" : ""}" data-${type}-input="${index}" ${sectionAttr} value="${escapeHtml(displayValue)}" placeholder="${placeholder}" aria-label="${isSection ? "ingredient section" : `${type} ${index + 1}`}" />`
        }
        <div class="parsed-edit-actions">
          <button
            type="button"
            class="parsed-row-button"
            data-${type}-convert-section="${index}"
            title="${isSection
              ? `Convert to ${type}`
              : `Convert to ${type} section`}"
            aria-label="${isSection
              ? `Convert to ${type}`
              : `Convert to ${type} section`}"
          >${isSection ? "↩ Row" : "§"}</button>
          ${reorderMode ? `<button type="button" class="parsed-row-button" data-${type}-up="${index}" aria-label="Move ${type} up">↑</button>` : ""}
          ${reorderMode ? `<button type="button" class="parsed-row-button" data-${type}-down="${index}" aria-label="Move ${type} down">↓</button>` : ""}
          <button type="button" class="parsed-row-button parsed-row-delete-button" data-${type}-delete="${index}" aria-label="Remove ${type}">✕</button>
        </div>
      </div>
    `;
    })
    .join("");
  containerEl.innerHTML = `<div class="parsed-edit-list">${rows}</div>`;
}

function renderOcrWarningBanner() {
  if (!ocrWarningBanner) return;
  const warning = String(formState.parsed.ocr_warning || "").trim();
  if (!warning) {
    ocrWarningBanner.classList.add("hidden");
    ocrWarningBanner.classList.remove("strong");
    ocrWarningBanner.textContent = "";
    return;
  }
  const warningLevel = String(formState.parsed.ocr_warning_level || "").trim().toLowerCase();
  const confidence = typeof formState.parsed.ocr_confidence === "number"
    ? Math.round(formState.parsed.ocr_confidence)
    : null;
  const severityPrefix = warningLevel === "strong" ? "⚠️ Strong warning: " : "⚠️ ";
  const confidenceText = confidence === null ? "" : ` (OCR confidence: ${confidence}%)`;
  ocrWarningBanner.textContent = `${severityPrefix}${warning}${confidenceText}`;
  ocrWarningBanner.classList.toggle("strong", warningLevel === "strong");
  ocrWarningBanner.classList.remove("hidden");
}

function renderParsedResults() {
  if (
    !parsedResultsSection ||
    !parsedServingsEl ||
    !parsedIngredientsEl ||
    !parsedInstructionsEl ||
    !parsedServingsSection ||
    !parsedIngredientsSection ||
    !parsedInstructionsSection
  ) return;

  const {
    servings,
    ingredients: parsedIngredients,
    instructions: parsedInstructions,
    ingredient_groups: parsedIngredientGroups,
    instruction_groups: parsedInstructionGroups
  } = formState.parsed;
  const normalizedServings = normalizeServingsDisplay(servings);
  const hasGroupedIngredients = hasNonEmptyGroups(parsedIngredientGroups, "items");
  const hasGroupedInstructions = hasNonEmptyGroups(parsedInstructionGroups, "steps");
  const hasFlatIngredients = hasNonEmptyItems(parsedIngredients);
  const hasFlatInstructions = hasNonEmptyItems(parsedInstructions);
  const hasServings = Boolean(normalizedServings);
  const hasIngredients = hasGroupedIngredients || hasFlatIngredients;
  const hasInstructions = hasGroupedInstructions || hasFlatInstructions;
  const isEditMode = Boolean(editIdInput?.value);
  const showIngredientsEditor = hasIngredients || isEditMode || addRecipeMode === "manual";
  const showInstructionsEditor = hasInstructions || isEditMode || addRecipeMode === "manual";
  const ingredientRenderSource = hasGroupedIngredients ? "grouped" : "flat";
  const instructionRenderSource = hasGroupedInstructions ? "grouped" : "flat";

  parsedServingsSection.classList.toggle("hidden", !hasServings);
  parsedIngredientsSection.classList.toggle("hidden", !showIngredientsEditor);
  parsedInstructionsSection.classList.toggle("hidden", !showInstructionsEditor);
  parsedServingsEl.textContent = normalizedServings || "";
  if (editServingsInput) editServingsInput.value = formState.parsed.servings || "";
  if (editPrepTimeInput) editPrepTimeInput.value = formState.parsed.prep_time || "";
  if (editCookTimeInput) editCookTimeInput.value = formState.parsed.cook_time || "";
  if (editTitleInput) editTitleInput.value = titleInput?.value || "";

  const editableIngredients = getEditableIngredients();
  const editableInstructions = getEditableInstructions();
  renderEditableList(parsedIngredientsEl, editableIngredients, {
    type: "ingredient",
    reorderMode: ingredientReorderMode
  });
  renderEditableList(parsedInstructionsEl, editableInstructions, {
    type: "instruction",
    reorderMode: instructionReorderMode
  });

  if (ingredientsReorderButton) ingredientsReorderButton.textContent = ingredientReorderMode ? "Done" : "Re-order";
  if (instructionsReorderButton) instructionsReorderButton.textContent = instructionReorderMode ? "Done" : "Re-order";
  if (addIngredientSectionButton) {
    addIngredientSectionButton.classList.toggle("hidden", !showIngredientsEditor);
  }
  if (addInstructionSectionButton) {
    addInstructionSectionButton.classList.toggle("hidden", !showInstructionsEditor);
  }

  if (pendingIngredientFocusIndex !== null) {
    const target = parsedIngredientsEl.querySelector(`[data-ingredient-input="${pendingIngredientFocusIndex}"]`);
    if (target) target.focus();
    pendingIngredientFocusIndex = null;
  }
  if (pendingInstructionFocusIndex !== null) {
    const target = parsedInstructionsEl.querySelector(`[data-instruction-input="${pendingInstructionFocusIndex}"]`);
    if (target) target.focus();
    pendingInstructionFocusIndex = null;
  }

  renderOcrWarningBanner();
}

function clearParsedState() {
  clearSocialResolutionDebug();
  ingredientReorderMode = false;
  instructionReorderMode = false;
  pendingIngredientFocusIndex = null;
  pendingInstructionFocusIndex = null;
  if (notesInput) notesInput.value = "";
  formState.parsed = {
    image_url: "",
    servings: "",
    prep_time: "",
    cook_time: "",
    total_time: "",
    prep_minutes: null,
    cook_minutes: null,
    total_minutes: null,
    ingredients: [],
    instructions: [],
    ingredient_groups: [],
    instruction_groups: [],
    metadata_extracted: false,
    ocr_confidence: null,
    ocr_warning: "",
    ocr_warning_level: ""
  };
  formState.import_context = {
    original_url: "",
    resolved_url: "",
    original_source_url: "",
    resolved_recipe_url: "",
    content_source: ""
  };
  renderParsedResults();
}

function applyParsedPreview(data) {
  formState.parsed.image_url = data.image_url || "";
  syncImageInputFromParsed();
  if (notesInput) notesInput.value = data.notes || "";
  formState.parsed.servings = data.servings || "";
  formState.parsed.prep_time = data.prep_time || "";
  formState.parsed.cook_time = data.cook_time || "";
  formState.parsed.total_time = data.total_time || "";
  formState.parsed.prep_minutes = data.prep_minutes ?? null;
  formState.parsed.cook_minutes = data.cook_minutes ?? null;
  formState.parsed.total_minutes = data.total_minutes ?? null;
  const incomingIngredientGroups = Array.isArray(data.ingredient_groups) ? data.ingredient_groups : [];
  const incomingInstructionGroups = Array.isArray(data.instruction_groups) ? data.instruction_groups : [];
  formState.parsed.ingredient_groups = incomingIngredientGroups;
  formState.parsed.instruction_groups = incomingInstructionGroups;
  formState.parsed.ingredients = incomingIngredientGroups.length
    ? []
    : (Array.isArray(data.ingredients) ? data.ingredients : []);
  formState.parsed.instructions = incomingInstructionGroups.length
    ? []
    : (Array.isArray(data.instructions) ? data.instructions : []);
  formState.parsed.metadata_extracted = true;
  formState.parsed.ocr_confidence = typeof data.ocr_confidence === "number" ? data.ocr_confidence : null;
  formState.parsed.ocr_warning = String(data.ocr_warning || "").trim();
  formState.parsed.ocr_warning_level = String(data.ocr_warning_level || "").trim();
  formState.parsed.ai_review_source_payload = data.ai_review_source_payload && typeof data.ai_review_source_payload === "object"
    ? data.ai_review_source_payload
    : null;
}

function buildCurrentParsedPreviewPayload() {
  const ingredientGroups = sanitizeIngredientGroups(formState.parsed.ingredient_groups);
  const instructionGroups = sanitizeInstructionGroups(formState.parsed.instruction_groups);
  return {
    title: (titleInput?.value || "").trim(),
    servings: ((editServingsInput?.value ?? formState.parsed.servings) || "").trim(),
    prep_time: ((editPrepTimeInput?.value ?? formState.parsed.prep_time) || "").trim(),
    cook_time: ((editCookTimeInput?.value ?? formState.parsed.cook_time) || "").trim(),
    ingredient_groups: ingredientGroups,
    instruction_groups: instructionGroups,
    ingredients: Array.isArray(formState.parsed.ingredients) ? formState.parsed.ingredients : [],
    instructions: Array.isArray(formState.parsed.instructions) ? formState.parsed.instructions : []
  };
}

function hasParsedCoreContent(parsed) {
  const normalizedIngredientGroups = sanitizeIngredientGroups(parsed?.ingredient_groups);
  const normalizedInstructionGroups = sanitizeInstructionGroups(parsed?.instruction_groups);
  const hasIngredients = normalizedIngredientGroups.some((group) => Array.isArray(group.items) && group.items.length > 0);
  const hasInstructions = normalizedInstructionGroups.some((group) => Array.isArray(group.steps) && group.steps.length > 0);
  if (hasIngredients || hasInstructions) return { hasIngredients, hasInstructions };
  return {
    hasIngredients: Array.isArray(parsed?.ingredients) && parsed.ingredients.length > 0,
    hasInstructions: Array.isArray(parsed?.instructions) && parsed.instructions.length > 0,
  };
}

function hasUsableRecipeMetadata(payload) {
  if (!payload || typeof payload !== "object") return false;
  const hasTitle = Boolean(String(payload.title || "").trim());
  const hasImage = Boolean(String(payload.image_url || "").trim());
  const hasServings = Boolean(String(payload.servings || "").trim());
  const { hasIngredients, hasInstructions } = hasParsedCoreContent(payload);
  return hasTitle || hasImage || hasServings || hasIngredients || hasInstructions;
}

function isNeedsReviewMetadataFallback(payload) {
  if (!payload || typeof payload !== "object") return false;
  if (String(payload.status || "").toLowerCase() === "needs_review") return true;
  return !hasUsableRecipeMetadata(payload);
}

function isSocialShareUrl(value) {
  const normalized = String(value || "").toLowerCase();
  return (
    normalized.includes("facebook.com") ||
    normalized.includes("fb.watch") ||
    normalized.includes("instagram.com") ||
    normalized.includes("instagr.am")
  );
}

function isFacebookInternalUrl(value) {
  const normalized = String(value || "").trim();
  if (!normalized) return false;
  try {
    const parsed = new URL(normalized);
    const host = parsed.hostname.toLowerCase();
    return host === "facebook.com" || host.endsWith(".facebook.com") || host === "fb.watch";
  } catch (_) {
    return normalized.toLowerCase().includes("facebook.com") || normalized.toLowerCase().includes("fb.watch");
  }
}

function isFacebookReelOrShareUrl(value) {
  const normalized = String(value || "").trim();
  if (!normalized) return false;
  try {
    const parsed = new URL(normalized);
    const host = parsed.hostname.toLowerCase();
    if (!(host === "facebook.com" || host.endsWith(".facebook.com"))) return false;
    const path = parsed.pathname.toLowerCase();
    return path.startsWith("/reel/") || path.startsWith("/share/");
  } catch (_) {
    const lowered = normalized.toLowerCase();
    return lowered.includes("facebook.com/reel/") || lowered.includes("facebook.com/share/");
  }
}

function getImportFallbackMessage(rawUrl, payload) {
  const reason = String(payload?.reason || "").trim();
  if (reason) return reason;
  if (isSocialShareUrl(rawUrl)) {
    return "We couldn’t extract the recipe directly, but we tried to locate the original recipe website. Try sharing the original recipe link or paste the recipe website directly.";
  }
  return "Couldn’t extract recipe details from this URL. Try opening the recipe page directly and paste that website link.";
}

function safeDecode(value) {
  if (!value) return "";
  try {
    return decodeURIComponent(value);
  } catch (_) {
    return value;
  }
}

async function enrichFromUrl() {
  if (isImportLoading) return false;
  stopImportProgress();
  applyAddRecipeMode("import");
  const rawUrl = urlInput.value.trim();
  if (!rawUrl) return;
  clearSocialResolutionDebug();

  // Strip noisy fbclid before request, while preserving user-visible raw URL on failure.
  const requestUrl = rawUrl.replace(/&fbclid=.*$/, "");
  if (isSocialShareUrl(rawUrl)) {
    startImportProgress([
      "Queued import…",
      "Downloading…",
      "Transcribing…",
      "Parsing…",
      "AI cleanup…",
      "Ready for review soon…"
    ]);
  } else {
    startImportProgress(["Queued import…", "Parsing…", "Ready for review soon…"]);
  }
  isImportLoading = true;
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.classList.toggle("disabled", true);
    submitButton.textContent = "⏳";
  }

  try {
    const res = await apiFetch(
      `${API_BASE}/extract-metadata?url=${encodeURIComponent(requestUrl)}`
    );
    if (!res.ok) {
      clearParsedState();
      showAddRecipeStatus("Couldn’t import this URL right now. Please try again.");
      return false;
    }

    const data = await res.json();
    const hasSocialMetadata = Boolean(data?.social_metadata && typeof data.social_metadata === "object");
    if (isSocialShareUrl(rawUrl) && hasSocialMetadata) {
      renderSocialResolutionDebug({
        originalUrl: rawUrl,
        socialMetadata: data.social_metadata,
        resolvedUrl: data.resolved_url || data.url || ""
      });
    } else {
      clearSocialResolutionDebug();
    }
    const fallbackRawUrl = String(data.source_url || rawUrl || "").trim() || rawUrl;
    if (isNeedsReviewMetadataFallback(data)) {
      clearParsedState();
      urlInput.value = fallbackRawUrl;
      showAddRecipeStatus(getImportFallbackMessage(fallbackRawUrl, data));
      return false;
    }

    if (data.url) urlInput.value = data.url;
    if (data.title) titleInput.value = data.title;
    if (data.source_app) sourceAppInput.value = data.source_app;
    if (data.source_type) sourceTypeInput.value = data.source_type;
    formState.import_context = {
      original_url: rawUrl,
      resolved_url: String(data.url || requestUrl || rawUrl).trim(),
      original_source_url: String(data.original_source_url || rawUrl).trim(),
      resolved_recipe_url: String(data.resolved_recipe_url || data.url || "").trim(),
      content_source: String(data.content_source || "").trim()
    };
    stopImportProgress();
    applyParsedPreview(data);
    showAddRecipeStatus("Parsing complete. Review and save when ready.", "info");
    applyAddRecipeMode("import", { parsed: true });
    renderParsedResults();
    return true;
  } catch (err) {
    stopImportProgress();
    console.log("enrich failed", err);
    clearParsedState();
    urlInput.value = rawUrl;
    showAddRecipeStatus("Couldn’t import this URL right now. Please try again.");
    return false;
  } finally {
    stopImportProgress();
    isImportLoading = false;
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.classList.toggle("disabled", false);
      submitButton.textContent = submitButtonDefaultLabel;
    }
  }
}

async function importFromImageFile(file) {
  if (!file || isImportLoading) return false;
  stopImportProgress();
  clearSocialResolutionDebug();
  clearAddRecipeStatus();
  startImportProgress(["Queued import…", "OCR processing…", "Parsing…", "Ready for review soon…"]);
  isImportLoading = true;
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.classList.toggle("disabled", true);
    submitButton.textContent = "⏳";
  }

  try {
    const formData = new FormData();
    formData.append("image", file);
    const response = await apiFetch(`${API_BASE}/import/image`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      let errorMessage = "Couldn’t import this image yet. Try another photo.";
      try {
        const payload = await response.json();
        if (payload?.detail) errorMessage = String(payload.detail);
      } catch (_error) {
        // Keep fallback message.
      }
      showAddRecipeStatus(errorMessage);
      return false;
    }

    const data = await response.json();
    showAddRecipeStatus("Parsing OCR text…", "info");
    if (!data || typeof data !== "object") {
      console.error("image import returned invalid response payload", data);
      showAddRecipeStatus("Couldn’t read OCR results from this image. Please try another photo.");
      return false;
    }
    const parsedIngredients = Array.isArray(data.ingredients) ? data.ingredients : [];
    const parsedInstructions = Array.isArray(data.instructions) ? data.instructions : [];
    if (!data.title && parsedIngredients.length === 0 && parsedInstructions.length === 0) {
      console.warn("image import response missing expected parsed fields", {
        keys: Object.keys(data),
        content_source: data.content_source
      });
    }
    titleInput.value = data.title || "";
    sourceAppInput.value = data.source_app || "Upload";
    sourceTypeInput.value = data.source_type || "Image";
    formState.import_context = {
      original_url: "",
      resolved_url: "",
      original_source_url: "",
      resolved_recipe_url: "",
      content_source: String(data.content_source || "image_ocr").trim() || "image_ocr",
    };
    stopImportProgress();
    applyParsedPreview(data);
    showAddRecipeStatus("Parsed recipe ready for review.", "info");
    applyAddRecipeMode("import", { parsed: true });
    renderParsedResults();
    if (parsedResultsSection) parsedResultsSection.classList.remove("hidden");
    if (importOptionGrid) importOptionGrid.classList.add("hidden");
    console.info("image import parsed preview applied", {
      parsedVisible: parsedResultsSection ? !parsedResultsSection.classList.contains("hidden") : null,
      mode: addRecipeMode,
      titlePresent: Boolean((data.title || "").trim()),
      ingredientCount: parsedIngredients.length,
      instructionCount: parsedInstructions.length,
      contentSource: formState.import_context.content_source
    });
    return true;
  } catch (err) {
    stopImportProgress();
    console.error("image import failed", err);
    showAddRecipeStatus("Couldn’t import this image right now. Please try again.");
    return false;
  } finally {
    stopImportProgress();
    isImportLoading = false;
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.classList.toggle("disabled", false);
      submitButton.textContent = submitButtonDefaultLabel;
    }
  }
}

async function runModalAiCleanup() {
  if (isModalAiCleanupRunning || isImportLoading) return;
  stopImportProgress();
  const cleanupUrl = String(formState.import_context.original_url || urlInput?.value || "").trim();
  if (!cleanupUrl) {
    showAddRecipeStatus("Paste and parse a recipe URL before running AI Cleanup.");
    return;
  }

  isModalAiCleanupRunning = true;
  if (runAiCleanupButton) {
    runAiCleanupButton.disabled = true;
    runAiCleanupButton.textContent = "Running AI cleanup...";
  }
  clearAddRecipeStatus();

  try {
    const response = await apiFetch(`${API_BASE}/recipes/modal-ai-cleanup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: cleanupUrl,
        preview: buildCurrentParsedPreviewPayload()
      })
    });
    if (!response.ok) {
      let cleanupError = "AI cleanup failed. You can still save the current parsed recipe.";
      try {
        const payload = await response.json();
        if (payload?.detail) cleanupError = String(payload.detail);
      } catch (_error) {
        // Keep fallback message.
      }
      showAddRecipeStatus(cleanupError);
      return;
    }

    const data = await response.json();
    const cleaned = data?.preview && typeof data.preview === "object" ? data.preview : null;
    if (!cleaned) {
      showAddRecipeStatus("AI cleanup returned an invalid preview. Keeping current parsed result.");
      return;
    }

    if (cleaned.title) {
      titleInput.value = cleaned.title;
    }
    applyParsedPreview(cleaned);
    renderParsedResults();
    showAddRecipeStatus("AI cleanup applied to preview. Review and click Add Recipe to save.");
  } catch (error) {
    console.log("modal ai cleanup failed", error);
    showAddRecipeStatus("AI cleanup failed. You can still save the current parsed recipe.");
  } finally {
    stopImportProgress();
    isModalAiCleanupRunning = false;
    if (runAiCleanupButton) {
      runAiCleanupButton.textContent = "Run AI Cleanup";
      runAiCleanupButton.disabled = false;
    }
    renderParsedResults();
  }
}

function extractUrlFromText(text) {
  const value = String(text || "").trim();
  if (!value) return "";
  const match = value.match(/https?:\/\/[^\s<>"']+/i);
  return match ? match[0].trim() : "";
}

function extractUrlsFromText(text) {
  if (!text) return [];
  return Array.from(String(text).matchAll(/https?:\/\/[^\s"'<>]+/gi))
    .map((match) => String(match[0] || "").replace(/[),.;!?]+$/, ""))
    .filter(Boolean);
}

function extractFacebookStructuredShareData(payload = {}) {
  const rawUrl = String(payload.url || "");
  if (!isFacebookReelOrShareUrl(rawUrl)) return null;

  const searchBlob = [payload.text, payload.title]
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .join("\n");
  if (!searchBlob) return null;

  const candidateUrls = [];
  const messageTexts = [];
  const thumbnailUrls = [];

  const collectStructuredFields = (value) => {
    if (!value || typeof value !== "object") return;

    if (typeof value.message?.text === "string" && value.message.text.trim()) {
      messageTexts.push(value.message.text.trim());
    }

    const ranges = Array.isArray(value.ranges) ? value.ranges : [];
    ranges.forEach((range) => {
      const entityUrl = String(range?.entity?.url || "").trim();
      if (entityUrl) candidateUrls.push(entityUrl);
      const entityType = String(range?.entity?.__typename || range?.entity?.type || "").toLowerCase();
      if (entityType.includes("externalurl") && entityUrl) {
        candidateUrls.unshift(entityUrl);
      }
    });

    const nestedCandidates = [
      value.url,
      value.permalink_url,
      value.permalinkUrl,
      value.shareable_url,
      value.shareableUrl,
      value.href
    ];
    nestedCandidates.forEach((candidate) => {
      if (typeof candidate === "string" && candidate.trim()) candidateUrls.push(candidate.trim());
    });

    const nestedThumbs = [
      value.thumbnail,
      value.thumbnail_url,
      value.thumbnailUrl,
      value.preview_image,
      value.previewImage,
      value.image?.uri,
      value.image?.url
    ];
    nestedThumbs.forEach((candidate) => {
      if (typeof candidate === "string" && candidate.trim()) thumbnailUrls.push(candidate.trim());
    });

    Object.values(value).forEach((child) => {
      if (!child || typeof child !== "object") return;
      if (Array.isArray(child)) {
        child.forEach((entry) => collectStructuredFields(entry));
        return;
      }
      collectStructuredFields(child);
    });
  };

  const jsonCandidates = Array.from(searchBlob.matchAll(/\{[\s\S]*?\}/g)).map((match) => match[0]);
  jsonCandidates.forEach((candidate) => {
    try {
      collectStructuredFields(JSON.parse(candidate));
    } catch (_) {
      // Ignore non-JSON snippets.
    }
  });

  const plainTextUrls = extractUrlsFromText(searchBlob);
  const caption = messageTexts.find(Boolean) || String(payload.text || "").trim();
  const orderedCandidates = [...candidateUrls, ...extractUrlsFromText(caption), ...plainTextUrls]
    .map((candidate) => candidate.trim())
    .filter(Boolean);
  const firstExternalUrl = orderedCandidates.find((candidate) => !isFacebookInternalUrl(candidate)) || "";
  const firstPreviewImage = thumbnailUrls.find((candidate) => !isFacebookInternalUrl(candidate)) || thumbnailUrls[0] || "";

  return {
    externalUrl: firstExternalUrl,
    caption,
    thumbnailUrl: firstPreviewImage
  };
}

function inferTitleFromUrl(value) {
  const trimmedValue = String(value || "").trim();
  if (!trimmedValue) return "Imported recipe";

  try {
    const parsed = new URL(trimmedValue);
    const hostLabel = parsed.hostname.replace(/^www\./i, "");
    const pathLabel = parsed.pathname
      .split("/")
      .filter(Boolean)
      .pop() || "";
    const decodedPath = decodeURIComponent(pathLabel)
      .replace(/[-_]+/g, " ")
      .replace(/\.[a-z0-9]+$/i, "")
      .trim();
    if (decodedPath) {
      return decodedPath
        .split(/\s+/)
        .map((part) => part ? `${part[0].toUpperCase()}${part.slice(1)}` : "")
        .join(" ");
    }
    return hostLabel || "Imported recipe";
  } catch (_) {
    return "Imported recipe";
  }
}

function normalizeUrlKey(url) {
  try {
    const parsed = new URL(String(url || "").trim());
    const normalizedPath = parsed.pathname.replace(/\/+$/, "") || "/";
    return `${parsed.protocol}//${parsed.host}${normalizedPath}${parsed.search}`.toLowerCase();
  } catch (_) {
    return String(url || "").trim().toLowerCase();
  }
}

function getPendingSharedPayload() {
  const pendingRaw = localStorage.getItem("recipe_clipper_pending_share");
  if (pendingRaw) {
    try {
      const parsed = JSON.parse(pendingRaw);
      if (parsed && typeof parsed === "object") {
        return {
          url: String(parsed.url || ""),
          text: String(parsed.text || ""),
          title: String(parsed.title || "")
        };
      }
    } catch (_) {
      // noop
    }
  }

  const legacyUrl = localStorage.getItem("shared_url") || "";
  const legacyText = localStorage.getItem("shared_text") || "";
  const legacyTitle = localStorage.getItem("shared_title") || "";
  if (legacyUrl || legacyText || legacyTitle) {
    return { url: legacyUrl, text: legacyText, title: legacyTitle };
  }
  return null;
}

function persistPendingSharedPayload(payload) {
  const nextPayload = {
    url: String(payload?.url || ""),
    text: String(payload?.text || ""),
    title: String(payload?.title || ""),
    captured_at: new Date().toISOString(),
    source: "app.js"
  };

  localStorage.setItem("recipe_clipper_pending_share", JSON.stringify(nextPayload));
  if (nextPayload.url) localStorage.setItem("shared_url", nextPayload.url);
  if (nextPayload.text) localStorage.setItem("shared_text", nextPayload.text);
  if (nextPayload.title) localStorage.setItem("shared_title", nextPayload.title);
}

function clearPendingSharedPayload() {
  localStorage.removeItem("recipe_clipper_pending_share");
  localStorage.removeItem("shared_url");
  localStorage.removeItem("shared_text");
  localStorage.removeItem("shared_title");
}

function captureSharedPayloadFromQuery() {
  const params = new URLSearchParams(window.location.search || "");
  const sharedPayload = {
    url: safeDecode(params.get("url") || ""),
    text: safeDecode(params.get("text") || ""),
    title: safeDecode(params.get("title") || "")
  };
  if (!sharedPayload.url && !sharedPayload.text && !sharedPayload.title) {
    return null;
  }
  persistPendingSharedPayload(sharedPayload);
  window.history.replaceState({}, document.title, `${window.location.pathname}${window.location.hash || ""}`);
  return sharedPayload;
}

function setShareImportState(nextState) {
  if (!shareImportPanel || !shareImportLabel || !shareImportTitle || !shareImportDetails || !shareImportActions) return;

  const defaultState = {
    label: "",
    title: "",
    details: "",
    showActions: false,
    openRecipeId: null,
    manualPayload: null,
    socialPreview: null
  };
  const state = { ...defaultState, ...(nextState || {}) };

  shareImportOpenRecipeId = state.openRecipeId ? String(state.openRecipeId) : null;
  shareImportManualPayload = state.manualPayload || null;

  if (!state.title) {
    shareImportPanel.classList.add("hidden");
    shareImportActions.classList.add("hidden");
    if (shareImportPreview) shareImportPreview.classList.add("hidden");
    return;
  }

  shareImportPanel.classList.remove("hidden");
  shareImportLabel.textContent = state.label;
  shareImportTitle.textContent = state.title;
  shareImportDetails.textContent = state.details;
  shareImportActions.classList.toggle("hidden", !state.showActions);

  const preview = state.socialPreview && typeof state.socialPreview === "object"
    ? state.socialPreview
    : null;
  const previewImage = String(preview?.thumbnailUrl || "").trim();
  const previewCaption = String(preview?.caption || "").trim();
  if (!shareImportPreview || !shareImportPreviewImage || !shareImportPreviewCaption) return;
  if (!previewImage && !previewCaption) {
    shareImportPreview.classList.add("hidden");
    return;
  }
  shareImportPreview.classList.remove("hidden");
  shareImportPreviewImage.classList.toggle("hidden", !previewImage);
  shareImportPreviewImage.src = previewImage || "";
  shareImportPreviewCaption.classList.toggle("hidden", !previewCaption);
  shareImportPreviewCaption.textContent = previewCaption;
}

function prefillManualShareForm(payload) {
  clearEditMode();
  form.reset();
  if (payload?.url) urlInput.value = payload.url;
  if (payload?.title) titleInput.value = payload.title;
  if (payload?.text) notesInput.value = payload.text;
  showAddRecipeModal();
}

function normalizeImportedRecipeTitle(value) {
  return String(value || "")
    .replace(/^\s{0,3}#{1,6}\s*/, "")
    .trim();
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function toDisplayHost(url) {
  const normalized = String(url || "").trim();
  if (!normalized) return "";
  try {
    return new URL(normalized).hostname.replace(/^www\./i, "");
  } catch (_) {
    return "";
  }
}

function getRecipeImage(recipe) {
  if (!recipe || typeof recipe !== "object") return "";

  const candidates = [
    recipe.image_url,
    recipe.imageUrl,
    recipe.image,
    recipe.thumbnail_url,
    recipe.thumbnailUrl,
    recipe.thumbnail
  ];

  const image = candidates.find((value) => typeof value === "string" && value.trim());
  return image ? image.trim() : "";
}

function syncImageInputFromParsed() {
  if (!imageUrlInput) return;
  if (imageUrlInput.value.trim()) return;
  imageUrlInput.value = formState.parsed.image_url || "";
}

function renderEditImagePreview() {
  const imageUrl = String(imageUrlInput?.value || "").trim();
  if (editImagePreview) {
    editImagePreview.src = imageUrl || "";
    editImagePreview.classList.toggle("hidden", !imageUrl);
  }
  if (editImagePlaceholder) {
    editImagePlaceholder.classList.toggle("hidden", Boolean(imageUrl));
  }
  if (clearEditImageButton) {
    clearEditImageButton.classList.toggle("hidden", !imageUrl);
    clearEditImageButton.disabled = !imageUrl;
  }
}

function startEdit(recipe) {
  editIdInput.value = recipe.id || "";
  applyAddRecipeMode("edit", { parsed: true });
  titleInput.value = recipe.title || "";
  urlInput.value = recipe.url || "";
  if (imageUrlInput) imageUrlInput.value = getRecipeImage(recipe);
  sourceAppInput.value = recipe.source_app || "";
  sourceTypeInput.value = recipe.source_type || "";
  notesInput.value = recipe.notes || "";
  tagsInput.value = recipe.tags || "";

  formState.parsed = {
    image_url: getRecipeImage(recipe),
    servings: recipe.servings || "",
    prep_time: recipe.prep_time || recipe.prepTime || "",
    cook_time: recipe.cook_time || recipe.cookTime || "",
    total_time: recipe.total_time || recipe.totalTime || "",
    prep_minutes: recipe.prep_minutes ?? recipe.prepMinutes ?? null,
    cook_minutes: recipe.cook_minutes ?? recipe.cookMinutes ?? null,
    total_minutes: recipe.total_minutes ?? recipe.totalMinutes ?? null,
    ingredients: Array.isArray(recipe.ingredients) ? recipe.ingredients : [],
    instructions: Array.isArray(recipe.instructions) ? recipe.instructions : [],
    ingredient_groups: sanitizeIngredientGroups(recipe.ingredient_groups),
    instruction_groups: sanitizeInstructionGroups(recipe.instruction_groups),
    metadata_extracted: false
  };
  formState.import_context = {
    original_url: recipe.original_source_url || recipe.url || "",
    resolved_url: recipe.url || "",
    original_source_url: recipe.original_source_url || "",
    resolved_recipe_url: recipe.resolved_recipe_url || recipe.url || "",
    content_source: recipe.content_source || "direct_recipe_url"
  };
  renderParsedResults();
  renderEditImagePreview();

  if (cancelEditButton) cancelEditButton.classList.remove("hidden");
  showAddRecipeModal();
}

function buildAiCleanupDraftRecipe(recipe, preview) {
  const cleanedPreview = preview && typeof preview === "object" ? preview : {};
  return {
    ...recipe,
    title: cleanedPreview.title || recipe.title || "",
    notes: cleanedPreview.notes || recipe.notes || "",
    servings: cleanedPreview.servings || recipe.servings || "",
    prep_time: cleanedPreview.prep_time || recipe.prep_time || recipe.prepTime || "",
    cook_time: cleanedPreview.cook_time || recipe.cook_time || recipe.cookTime || "",
    total_time: cleanedPreview.total_time || recipe.total_time || recipe.totalTime || "",
    ingredients: Array.isArray(cleanedPreview.ingredients) ? cleanedPreview.ingredients : recipe.ingredients,
    instructions: Array.isArray(cleanedPreview.instructions) ? cleanedPreview.instructions : recipe.instructions,
    ingredient_groups: sanitizeIngredientGroups(cleanedPreview.ingredient_groups).length
      ? cleanedPreview.ingredient_groups
      : recipe.ingredient_groups,
    instruction_groups: sanitizeInstructionGroups(cleanedPreview.instruction_groups).length
      ? cleanedPreview.instruction_groups
      : recipe.instruction_groups
  };
}

function normalizeAiCleanupTextList(items = []) {
  return Array.isArray(items)
    ? items.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
}

function formatAiCleanupQuantity(value) {
  if (!Number.isFinite(value) || value <= 0) return "";
  const roundedWhole = Math.round(value);
  if (Math.abs(value - roundedWhole) < 0.000001) return String(roundedWhole);

  const whole = Math.floor(value);
  const fractional = value - whole;
  const knownFractions = [
    { value: 0.25, text: "1/4" },
    { value: 1 / 3, text: "1/3" },
    { value: 0.5, text: "1/2" },
    { value: 0.75, text: "3/4" }
  ];
  const matchedFraction = knownFractions.find(({ value: known }) => Math.abs(fractional - known) < 0.01);
  if (matchedFraction) {
    return whole > 0 ? `${whole} ${matchedFraction.text}` : matchedFraction.text;
  }

  return String(Number(value.toFixed(6)));
}

function normalizeAiCleanupIngredientParts(parts = []) {
  const cleanedParts = parts
    .map((part) => String(part ?? "").trim())
    .filter(Boolean);
  if (!cleanedParts.length) return "";

  let quantity = "";
  let unit = "";
  const remaining = [];

  for (let index = 0; index < cleanedParts.length; index += 1) {
    const part = cleanedParts[index];
    if (!quantity && parseNumberToken(part) !== null) {
      quantity = part;
      continue;
    }
    if (!unit) {
      const nextPart = cleanedParts[index + 1] || "";
      if (shouldMergeSuspiciousSingleLetterUnitFragment(part, nextPart)) {
        remaining.push(`${part}${nextPart}`);
        index += 1;
        continue;
      }
      const parsedUnit = parseLeadingUnit(part);
      if (parsedUnit && !parsedUnit.rest) {
        unit = pluralizedUnit(parsedUnit, parseNumberToken(quantity || "1") || 1);
        continue;
      }
    }
    remaining.push(part);
  }

  if (!remaining.length) return cleanedParts.join(" ");
  const [name, ...extras] = remaining.sort((left, right) => right.length - left.length);
  const formattedQuantity = parseNumberToken(quantity) !== null
    ? formatAiCleanupQuantity(parseNumberToken(quantity))
    : quantity;
  return [formattedQuantity, unit, name, ...extras].filter(Boolean).join(" ");
}

function tryParseAiCleanupSerializedIngredient(raw) {
  const value = String(raw || "").trim();
  if (!value) return null;

  const tupleMatch = value.match(/^\(?\s*['"](.+?)['"]\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*['"]([^'"]+)['"]\s*\)?$/);
  if (tupleMatch) {
    return normalizeAiCleanupIngredientParts([tupleMatch[1], tupleMatch[2], tupleMatch[3]]);
  }

  if ((value.startsWith("[") && value.endsWith("]")) || (value.startsWith("{") && value.endsWith("}"))) {
    try {
      const parsed = JSON.parse(value);
      return normalizeAiCleanupIngredientValue(parsed);
    } catch (_error) {
      return null;
    }
  }

  return null;
}

function normalizeAiCleanupIngredientValue(value) {
  if (value == null) return "";
  if (Array.isArray(value)) {
    return normalizeAiCleanupIngredientParts(
      value.map((item) => normalizeAiCleanupIngredientValue(item)).filter(Boolean)
    );
  }
  if (typeof value === "object") {
    const displayTextValue = String(value.display_text || value.displayText || value.raw || "").trim();
    if (displayTextValue) return normalizeAiCleanupIngredientValue(displayTextValue);

    const textValue = String(value.text || "").trim();
    if (textValue) return normalizeAiCleanupIngredientValue(textValue);

    const componentOrder = [
      "amount",
      "quantity",
      "unit",
      "name",
      "item",
      "ingredient",
      "description",
      "notes",
      "weight",
      "note",
      "preparation",
      "prep"
    ];
    const orderedParts = componentOrder
      .map((key) => normalizeAiCleanupIngredientValue(value[key]))
      .filter(Boolean);
    if (orderedParts.length) return normalizeAiCleanupIngredientParts(orderedParts);

    return "";
  }

  const stringValue = String(value).trim();
  if (!stringValue) return "";
  const parsedSerialized = tryParseAiCleanupSerializedIngredient(stringValue);
  const normalizedLine = parsedSerialized || stringValue;
  const collapsed = normalizedLine
    .replace(/\s+\./g, ".")
    .replace(/([A-Za-z]{4,})\.(?=\s+\w)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();

  const parsedQuantity = parseLeadingQuantity(collapsed);
  if (!parsedQuantity) return collapsed;

  const quantityText = formatAiCleanupQuantity(parsedQuantity.quantity) || collapsed;
  if (!quantityText) return collapsed;

  const repairedRemaining = repairSuspiciousSingleLetterUnitFragment(parsedQuantity.remaining);
  return `${quantityText} ${repairedRemaining}`.trim();
}

function normalizeAiCleanupRecipe(recipe) {
  const ingredientGroups = sanitizeIngredientGroups(recipe?.ingredient_groups);
  const instructionGroups = sanitizeInstructionGroups(recipe?.instruction_groups);
  const ingredients = ingredientGroups.length
    ? ingredientGroups.flatMap((group) => group.items)
    : (Array.isArray(recipe?.ingredients)
      ? recipe.ingredients.map((item) => normalizeAiCleanupIngredientValue(item)).filter(Boolean)
      : []);
  const instructions = instructionGroups.length
    ? instructionGroups.flatMap((group) => group.steps)
    : normalizeAiCleanupTextList(recipe?.instructions);

  return {
    title: String(recipe?.title || "").trim(),
    notes: String(recipe?.notes || "").trim(),
    servings: String(recipe?.servings || "").trim(),
    prep_time: String(recipe?.prep_time || recipe?.prepTime || "").trim(),
    cook_time: String(recipe?.cook_time || recipe?.cookTime || "").trim(),
    total_time: String(recipe?.total_time || recipe?.totalTime || "").trim(),
    ingredient_groups: ingredientGroups,
    ingredients,
    instruction_groups: instructionGroups,
    instructions
  };
}

function buildRecipeSavePayloadFromRecipe(recipe) {
  const normalized = normalizeAiCleanupRecipe(recipe);
  const payload = {
    title: normalized.title || inferTitleFromUrl(String(recipe?.url || "").trim()),
    url: String(recipe?.url || "").trim(),
    original_source_url: String(recipe?.original_source_url || "").trim() || null,
    resolved_recipe_url: String(recipe?.resolved_recipe_url || recipe?.url || "").trim() || null,
    content_source: String(recipe?.content_source || "direct_recipe_url").trim(),
    image_url: String(recipe?.image_url || getRecipeImage(recipe) || "").trim(),
    source_app: String(recipe?.source_app || "").trim() || "Chrome",
    source_type: String(recipe?.source_type || "").trim() || "Web",
    notes: String(recipe?.notes || ""),
    tags: String(recipe?.tags || ""),
    needs_review: false,
    review_status: "none",
    servings: normalized.servings,
    prep_time: normalized.prep_time,
    cook_time: normalized.cook_time,
    total_time: normalized.total_time,
    prep_minutes: recipe?.prep_minutes ?? null,
    cook_minutes: recipe?.cook_minutes ?? null,
    total_minutes: recipe?.total_minutes ?? null,
    ingredients: normalized.ingredients,
    instructions: normalized.instructions,
    ingredient_groups: normalized.ingredient_groups,
    instruction_groups: normalized.instruction_groups
  };

  if (!payload.url) {
    payload.url = "";
    payload.original_source_url = null;
    payload.resolved_recipe_url = null;
  }

  return payload;
}

function buildAiCleanupReviewChanges(recipe, preview) {
  const current = normalizeAiCleanupRecipe(recipe);
  const proposed = normalizeAiCleanupRecipe(buildAiCleanupDraftRecipe(recipe, preview));
  const fields = [
    { key: "title", label: "Title", type: "text" },
    { key: "notes", label: "Notes", type: "multiline" },
    { key: "servings", label: "Servings", type: "text" },
    { key: "prep_time", label: "Prep Time", type: "text" },
    { key: "cook_time", label: "Cook Time", type: "text" },
    { key: "total_time", label: "Total Time", type: "text" },
    { key: "ingredient_groups", label: "Ingredient Groups", type: "ingredient-groups" },
    ...(current.ingredient_groups.length || proposed.ingredient_groups.length
      ? []
      : [{ key: "ingredients", label: "Ingredients", type: "list" }]),
    { key: "instruction_groups", label: "Instruction Groups", type: "instruction-groups" },
    ...(current.instruction_groups.length || proposed.instruction_groups.length
      ? []
      : [{ key: "instructions", label: "Instructions", type: "ordered-list" }])
  ];

  const canonicalizeText = (value) => String(value || "").trim().toLowerCase();
  const canonicalizeList = (items = []) =>
    normalizeAiCleanupTextList(items).map((item) => canonicalizeText(item));
  const canonicalizeGroups = (groups = [], key) =>
    (Array.isArray(groups) ? groups : [])
      .map((group) => ({
        title: canonicalizeText(group?.title || ""),
        [key]: canonicalizeList(group?.[key] || [])
      }))
      .filter((group) => group[key].length);
  const hasMeaningfulDifference = ({ key, type }) => {
    const currentValue = current[key];
    const proposedValue = proposed[key];

    if (type === "ingredient-groups") {
      return JSON.stringify(canonicalizeGroups(currentValue, "items")) !== JSON.stringify(canonicalizeGroups(proposedValue, "items"));
    }
    if (type === "instruction-groups") {
      return JSON.stringify(canonicalizeGroups(currentValue, "steps")) !== JSON.stringify(canonicalizeGroups(proposedValue, "steps"));
    }
    if (type === "list" || type === "ordered-list") {
      return JSON.stringify(canonicalizeList(currentValue)) !== JSON.stringify(canonicalizeList(proposedValue));
    }
    return canonicalizeText(currentValue) !== canonicalizeText(proposedValue);
  };

  const changes = fields.filter(hasMeaningfulDifference);
  const canonicalRecipe = (value) => ({
    title: canonicalizeText(value?.title),
    notes: canonicalizeText(value?.notes),
    servings: canonicalizeText(value?.servings),
    prep_time: canonicalizeText(value?.prep_time),
    cook_time: canonicalizeText(value?.cook_time),
    total_time: canonicalizeText(value?.total_time),
    ingredient_groups: canonicalizeGroups(value?.ingredient_groups, "items"),
    ingredients: canonicalizeList(value?.ingredients),
    instruction_groups: canonicalizeGroups(value?.instruction_groups, "steps"),
    instructions: canonicalizeList(value?.instructions)
  });
  const normalizedChanges = JSON.stringify(canonicalRecipe(current)) === JSON.stringify(canonicalRecipe(proposed))
    ? []
    : changes;

  return {
    recipeId: String(recipe?.id || "").trim(),
    current,
    proposed,
    draftRecipe: buildAiCleanupDraftRecipe(recipe, preview),
    changes: normalizedChanges
  };
}

function renderAiCleanupReviewText(value) {
  const lines = String(value || "").split(/\r?\n/);
  if (!lines.some((line) => line.trim())) {
    return '<p class="ai-cleanup-review-empty">Empty</p>';
  }
  return lines.map((line) => `<p>${escapeHtml(line)}</p>`).join("");
}

function renderAiCleanupReviewList(items = [], ordered = false) {
  const normalizedItems = normalizeAiCleanupTextList(items);
  if (!normalizedItems.length) {
    return '<p class="ai-cleanup-review-empty">Empty</p>';
  }
  const tag = ordered ? "ol" : "ul";
  const itemsMarkup = normalizedItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  return `<${tag}>${itemsMarkup}</${tag}>`;
}

function renderAiCleanupReviewGroups(groups = [], key) {
  const normalizedGroups = key === "items"
    ? sanitizeIngredientGroups(groups)
    : sanitizeInstructionGroups(groups);
  if (!normalizedGroups.length) {
    return '<p class="ai-cleanup-review-empty">Empty</p>';
  }
  return normalizedGroups.map((group) => {
    const groupTitle = String(group?.title || "").trim();
    const values = Array.isArray(group?.[key]) ? group[key] : [];
    const titleMarkup = groupTitle && !isGenericRecipeSectionTitle(groupTitle, key)
      ? `<p class="ai-cleanup-review-group-title">${escapeHtml(groupTitle)}</p>`
      : "";
    const listMarkup = key === "steps"
      ? renderAiCleanupReviewList(values, true)
      : renderAiCleanupReviewList(values, false);
    return `<div class="ai-cleanup-review-group">${titleMarkup}${listMarkup}</div>`;
  }).join("");
}

function renderAiCleanupReviewValue(type, value) {
  if (type === "multiline") return renderAiCleanupReviewText(value);
  if (type === "list") return renderAiCleanupReviewList(value, false);
  if (type === "ordered-list") return renderAiCleanupReviewList(value, true);
  if (type === "ingredient-groups") return renderAiCleanupReviewGroups(value, "items");
  if (type === "instruction-groups") return renderAiCleanupReviewGroups(value, "steps");
  return renderAiCleanupReviewText(value);
}

function countDuplicateStrings(items = []) {
  const counts = new Map();
  normalizeAiCleanupTextList(items).forEach((item) => {
    counts.set(item, (counts.get(item) || 0) + 1);
  });
  return Array.from(counts.values()).filter((count) => count > 1).length;
}

function getAiCleanupReviewExplanation(change, review) {
  const currentValue = review?.current?.[change.key];
  const proposedValue = review?.proposed?.[change.key];

  if (change.key === "title") {
    return "This title is more specific, which makes the recipe easier to recognize later.";
  }

  if (change.key === "notes") {
    return "This keeps reference or serving details in Notes so the cooking steps stay easier to scan.";
  }

  if (change.key === "servings" || change.key === "prep_time" || change.key === "cook_time" || change.key === "total_time") {
    return "This standardizes the recipe details so the key metadata is clearer at a glance.";
  }

  if (change.key === "ingredient_groups") {
    const currentGroups = Array.isArray(currentValue) ? currentValue : [];
    const proposedGroups = Array.isArray(proposedValue) ? proposedValue : [];
    if (proposedGroups.length < currentGroups.length) {
      return "This combines ingredient sections to simplify the recipe and reduce unnecessary separation.";
    }
    if (proposedGroups.length > currentGroups.length) {
      return "This separates the ingredients into clearer sections so the recipe is easier to organize.";
    }
    return "This renames or reorganizes the ingredient sections to make the recipe structure clearer.";
  }

  if (change.key === "ingredients") {
    if (countDuplicateStrings(proposedValue) < countDuplicateStrings(currentValue)) {
      return "This removes duplicate ingredient entries so the shopping and prep lists stay cleaner.";
    }
    const currentItems = normalizeAiCleanupTextList(currentValue);
    const proposedItems = normalizeAiCleanupTextList(proposedValue);
    if (currentItems.length !== proposedItems.length) {
      return "This trims or consolidates the ingredient list so it is easier to read.";
    }
    return "This clarifies the ingredient wording so each item is easier to understand.";
  }

  if (change.key === "instruction_groups") {
    const currentGroups = Array.isArray(currentValue) ? currentValue : [];
    const proposedGroups = Array.isArray(proposedValue) ? proposedValue : [];
    if (proposedGroups.length < currentGroups.length) {
      return "This combines instruction sections to keep the cooking flow more straightforward.";
    }
    if (proposedGroups.length > currentGroups.length) {
      return "This adds clearer instruction sections so the recipe steps are easier to follow.";
    }
    return "This reorganizes the instruction sections to improve recipe flow and readability.";
  }

  if (change.key === "instructions") {
    if (countDuplicateStrings(proposedValue) < countDuplicateStrings(currentValue)) {
      return "This removes repeated instructions so the recipe is easier to follow.";
    }
    const currentSteps = normalizeAiCleanupTextList(currentValue);
    const proposedSteps = normalizeAiCleanupTextList(proposedValue);
    if (currentSteps.length !== proposedSteps.length) {
      return "This simplifies the cooking steps so the recipe reads more clearly from start to finish.";
    }
    return "This clarifies the cooking steps so each action is easier to follow.";
  }

  return "This change improves the recipe structure and clarity.";
}

function setAiCleanupReviewStatus(message = "", tone = "info") {
  if (!aiCleanupReviewStatus) return;
  const text = String(message || "").trim();
  aiCleanupReviewStatus.textContent = text;
  aiCleanupReviewStatus.classList.toggle("hidden", !text);
  aiCleanupReviewStatus.classList.toggle("success", tone === "success");
  aiCleanupReviewStatus.classList.toggle("error", tone === "error");
  aiCleanupReviewStatus.classList.toggle("info", tone === "info");
}

function renderAiCleanupReview(review) {
  if (!aiCleanupReviewChanges) return;
  if (!review?.changes?.length) {
    aiCleanupReviewChanges.innerHTML = '<p class="ai-cleanup-review-no-changes">No meaningful improvements recommended.</p>';
    return;
  }

  aiCleanupReviewChanges.innerHTML = review.changes.map(({ key, label, type }) => `
    <section class="ai-cleanup-review-section" data-ai-cleanup-field="${escapeHtml(key)}">
      <h4>${escapeHtml(label)}</h4>
      <p class="ai-cleanup-review-explanation">${escapeHtml(getAiCleanupReviewExplanation({ key, label, type }, review))}</p>
      <div class="ai-cleanup-review-grid">
        <div class="ai-cleanup-review-column">
          <span class="ai-cleanup-review-label">Current</span>
          <div class="ai-cleanup-review-value">${renderAiCleanupReviewValue(type, review.current[key])}</div>
        </div>
        <div class="ai-cleanup-review-column">
          <span class="ai-cleanup-review-label">Proposed</span>
          <div class="ai-cleanup-review-value">${renderAiCleanupReviewValue(type, review.proposed[key])}</div>
        </div>
      </div>
    </section>
  `).join("");
}

function showAiCleanupReview(review) {
  pendingAiCleanupReview = review;
  setAiCleanupReviewStatus("");
  renderAiCleanupReview(review);
  if (!aiCleanupReviewModal) return;
  aiCleanupReviewModal.classList.remove("hidden");
  aiCleanupReviewModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function hideAiCleanupReview() {
  pendingAiCleanupReview = null;
  if (aiCleanupReviewChanges) aiCleanupReviewChanges.innerHTML = "";
  setAiCleanupReviewStatus("");
  if (!aiCleanupReviewModal) return;
  aiCleanupReviewModal.classList.add("hidden");
  aiCleanupReviewModal.setAttribute("aria-hidden", "true");
  if (addRecipeModal?.classList.contains("hidden")) {
    document.body.classList.remove("modal-open");
  }
}

function clearEditMode() {
  editIdInput.value = "";
  if (imageUrlInput) imageUrlInput.value = "";
  if (editImageInput) editImageInput.value = "";
  renderEditImagePreview();
  if (cancelEditButton) cancelEditButton.classList.add("hidden");
  clearParsedState();
}

function hasNonEmptyItems(items = []) {
  return Array.isArray(items) && items.some((item) => String(item || "").trim());
}

function hasNonEmptyGroups(groups = [], key) {
  return Array.isArray(groups) && groups.some((group) =>
    Array.isArray(group?.[key]) &&
    group[key].some((item) => String(item || "").trim())
  );
}

function applyAddRecipeMode(mode, options = {}) {
  if (!form || !addRecipeModal) return;
  addRecipeMode = mode;
  const isChoose = mode === "choose";
  const isImport = mode === "import";
  const isPaste = mode === "paste";
  const isManual = mode === "manual";
  const isEdit = mode === "edit";
  const parsedReady = Boolean(options.parsed);
  const showRecipeDetails = isManual || isEdit || ((isImport || isPaste) && parsedReady);
  const showParsedResults = showRecipeDetails;
  const shouldShowSaveButtons = showRecipeDetails;

  if (addRecipeModalTitle) {
    addRecipeModalTitle.textContent = isEdit ? "Edit recipe" : "Add recipe";
    addRecipeModalTitle.classList.remove("hidden");
  }
  if (parsedResultsTitle) parsedResultsTitle.textContent = (isManual || isEdit) ? "Recipe contents" : "Parsed Recipe";
  if (importOptionGrid) importOptionGrid.classList.toggle("hidden", !isChoose);
  if (importBrowserPanel) importBrowserPanel.classList.toggle("hidden", !isImport);
  if (pasteTextPanel) pasteTextPanel.classList.toggle("hidden", !isPaste);
  if (editFieldsPanel) editFieldsPanel.classList.toggle("hidden", !showRecipeDetails);
  if (parsedResultsSection) parsedResultsSection.classList.toggle("hidden", !showParsedResults);
  if (importModeSeparator) importModeSeparator.classList.toggle("hidden", !(isImport || isPaste));
  if (importDivider) importDivider.classList.add("hidden");
  if (editImagePanel) editImagePanel.classList.toggle("hidden", !isEdit);
  if (runAiCleanupButton) {
    runAiCleanupButton.classList.toggle("hidden", !(isImport && parsedReady));
    runAiCleanupButton.disabled = !(isImport && parsedReady) || isModalAiCleanupRunning;
  }
  if (addRecipeSubmitButton) {
    addRecipeSubmitButton.textContent = (isManual || isEdit) ? "Save Recipe" : "Add Recipe";
    addRecipeSubmitButton.classList.toggle("hidden", !shouldShowSaveButtons);
    addRecipeSubmitButton.disabled = !shouldShowSaveButtons;
  }
  if (bottomSaveRecipeButton) {
    bottomSaveRecipeButton.textContent = (isManual || isEdit) ? "Save Recipe" : "Add Recipe";
    bottomSaveRecipeButton.classList.toggle("hidden", !shouldShowSaveButtons);
    bottomSaveRecipeButton.disabled = !shouldShowSaveButtons;
  }
  renderEditImagePreview();
}


function resetAddRecipeModalState() {
  if (!form) return;
  stopImportProgress();
  form.reset();
  editIdInput.value = "";
  if (imageUrlInput) imageUrlInput.value = "";
  if (editImageInput) editImageInput.value = "";
  if (cancelEditButton) cancelEditButton.classList.add("hidden");
  clearParsedState();
  if (pasteRecipeTextInput) pasteRecipeTextInput.value = "";
  if (urlInput) urlInput.value = "";
  if (imageUploadInput) imageUploadInput.value = "";
  clearAddRecipeStatus();
  document.body.classList.remove("modal-open");
  applyAddRecipeMode("choose");
}

function startManualRecipe() {
  if (!form) return;
  form.reset();
  editIdInput.value = "";
  clearParsedState();
  formState.parsed.ingredients = [""];
  formState.parsed.instructions = [""];
  formState.parsed.ingredient_groups = [{ title: "", items: [""] }];
  formState.parsed.instruction_groups = [{ title: "", steps: [""] }];
  sourceAppInput.value = "Manual";
  sourceTypeInput.value = "Manual";
  formState.import_context = {
    original_url: "",
    resolved_url: "",
    original_source_url: "",
    resolved_recipe_url: "",
    content_source: "manual"
  };
  applyAddRecipeMode("manual");
  renderParsedResults();
  showAddRecipeModal();
  editTitleInput?.focus();
}

function showAddRecipeModal() {
  if (!isAuthenticated()) return;
  if (!addRecipeModal) return;
  clearAddRecipeStatus();
  if (!editIdInput?.value && addRecipeMode !== "import" && addRecipeMode !== "paste" && addRecipeMode !== "manual") {
    applyAddRecipeMode("choose");
  }
  addRecipeModal.classList.remove("hidden");
  addRecipeModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function hideAddRecipeModal() {
  if (!addRecipeModal) return;
  stopImportProgress();
  addRecipeModal.classList.add("hidden");
  addRecipeModal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
  if (!isRecipeSaving) resetAddRecipeModalState();
}

function showRecipeDetail(recipe) {
  if (
    !recipeDetailView ||
    !detailTitleEl ||
    !detailIngredientsEl ||
    !detailInstructionsEl
  ) return;

  detailTitleEl.textContent = recipe.title || "Untitled recipe";
  if (detailReviewStatusEl) {
    const reviewStatus = String(recipe.review_status || "").toLowerCase();
    const statusLabel = {
      queued: "Queued for AI review",
      processing: "Processing...",
      failed: "AI review failed"
    }[reviewStatus] || "";
    detailReviewStatusEl.textContent = statusLabel;
    detailReviewStatusEl.classList.toggle("hidden", !statusLabel);
  }
  setDetailAiCleanupStatus("idle");
  if (detailAiCleanupButton) {
    detailAiCleanupButton.disabled = false;
    detailAiCleanupButton.textContent = "AI Cleanup";
  }
  const detailReviewStatus = String(recipe.review_status || "").toLowerCase();
  if (detailReviewStatus === "queued" || detailReviewStatus === "processing") {
    startReviewStatusPolling(recipe.id);
  } else {
    stopReviewStatusPolling();
  }
  const prepTime = normalizeTimeLabel(recipe.prep_time || recipe.prepTime || "");
  const cookTime = normalizeTimeLabel(recipe.cook_time || recipe.cookTime || "");
  if (detailPrepTimeEl) {
    detailPrepTimeEl.textContent = `Prep: ${prepTime}`;
    detailPrepTimeEl.classList.toggle("hidden", !prepTime);
  }
  if (detailCookTimeEl) {
    detailCookTimeEl.textContent = `Cook: ${cookTime}`;
    detailCookTimeEl.classList.toggle("hidden", !cookTime);
  }
  if (detailMetaRowEl) {
    detailMetaRowEl.classList.toggle("hidden", !prepTime && !cookTime);
  }

  const imageUrl = getRecipeImage(recipe);
  if (detailImageWrapEl && detailImageEl && detailImagePlaceholderEl) {
    detailImageEl.src = imageUrl || "";
    detailImageEl.classList.toggle("hidden", !imageUrl);
    detailImagePlaceholderEl.classList.toggle("hidden", Boolean(imageUrl));
    detailImageEl.alt = recipe.title
      ? `${recipe.title} recipe image`
      : "Recipe image";
    detailImageEl.onerror = () => {
      detailImageEl.classList.add("hidden");
      detailImagePlaceholderEl.classList.remove("hidden");
    };
    detailImageEl.onload = () => {
      if (!detailImageEl.src) return;
      detailImageEl.classList.remove("hidden");
      detailImagePlaceholderEl.classList.add("hidden");
    };
  }

  formState.selectedRecipe = recipe;
  currentDetailRecipeId = String(recipe.id || "").trim();
  const baseServings = parseServingsCount(recipe.servings);
  detailIngredientDisplayState = {
    baseServings,
    targetServings: baseServings,
    convertMode: getRecipeMeasurementMode(recipe)
  };
  if (detailServingsValueEl) {
    detailServingsValueEl.textContent = formatKitchenQuantity(baseServings) || "1";
  }
  if (detailServingsDecreaseButton) {
    detailServingsDecreaseButton.disabled = detailIngredientDisplayState.targetServings <= 1;
  }
  setDetailConvertMode(detailIngredientDisplayState.convertMode);
  const localDetailState = getRecipeDetailState(recipe);
  if (detailCookedToggle) detailCookedToggle.checked = localDetailState.cooked;
  if (detailNoteInput) detailNoteInput.value = localDetailState.note || "";
  updateRatingUi(localDetailState.rating);
  renderDetailCookbookMembership(recipe);
  toggleDetailCookbookPopover(false);
  closeDetailActionsMenu();

  renderDetailIngredients(recipe);
  if (copyIngredientsButton) {
    const hasIngredients = sanitizeIngredientGroups(recipe.ingredient_groups)
      .some((group) => Array.isArray(group.items) && group.items.length > 0);
    copyIngredientsButton.disabled = !hasIngredients;
  }
  if (detailShareButton) {
    const hasIngredients = sanitizeIngredientGroups(recipe.ingredient_groups).some((group) => group.items.length > 0);
    const hasInstructions = sanitizeInstructionGroups(recipe.instruction_groups).some((group) => group.steps.length > 0);
    detailShareButton.disabled = !(String(recipe.title || "").trim() && (hasIngredients || hasInstructions));
  }
  const instructionGroups = sanitizeInstructionGroups(recipe.instruction_groups);
  const recipeNotes = String(recipe.notes || "").trim();
  if (detailRecipeNotesSectionEl && detailRecipeNotesEl) {
    detailRecipeNotesEl.textContent = recipeNotes;
    detailRecipeNotesSectionEl.classList.toggle("hidden", !recipeNotes);
  }
  detailInstructionsEl.innerHTML = renderGroupedList(instructionGroups, "steps")
    || "<li class=\"detail-empty-item\">No instructions available.</li>";
  if (openOriginalButton) {
    const sourceRecipeUrl = String(recipe.resolved_recipe_url || recipe.url || "").trim();
    openOriginalButton.href = sourceRecipeUrl || "#";
    openOriginalButton.classList.toggle("disabled", !sourceRecipeUrl);
    openOriginalButton.setAttribute("aria-disabled", sourceRecipeUrl ? "false" : "true");
  }
  if (detailSourceLinksEl && detailSourceRecipeLinkEl && detailImportedFromLinkEl) {
    const sourceRecipeUrl = String(recipe.resolved_recipe_url || "").trim();
    const importedFromUrl = String(recipe.original_source_url || "").trim();
    const fallbackUrl = String(recipe.url || "").trim();
    const effectiveSourceUrl = sourceRecipeUrl || (!importedFromUrl ? fallbackUrl : "");
    const showImported = Boolean(importedFromUrl && importedFromUrl !== effectiveSourceUrl);
    const sourceAppLabel = String(recipe.source_app || "").trim();
    const importedFromLabel = sourceAppLabel
      ? `Imported from ${sourceAppLabel}`
      : `Imported from ${toDisplayHost(importedFromUrl) || "source"}`;

    detailSourceRecipeLinkEl.href = effectiveSourceUrl || "#";
    detailSourceRecipeLinkEl.textContent = "Source recipe";
    detailSourceRecipeLinkEl.title = effectiveSourceUrl || "";
    detailSourceRecipeLinkEl.classList.toggle("hidden", !effectiveSourceUrl);

    const importedLinkUrl = showImported ? importedFromUrl : "";
    detailImportedFromLinkEl.href = importedLinkUrl || "#";
    detailImportedFromLinkEl.textContent = importedFromLabel;
    detailImportedFromLinkEl.title = importedLinkUrl || "";
    detailImportedFromLinkEl.classList.toggle("hidden", !importedLinkUrl);

    detailSourceLinksEl.classList.toggle("hidden", !effectiveSourceUrl && !importedLinkUrl);
  }

  recipeDetailView.classList.remove("hidden");
  hideShoppingListView();
  recipesContainer.classList.add("hidden");
  if (recipesListHeader) recipesListHeader.classList.add("hidden");
  if (emptyState) emptyState.classList.add("hidden");
  if (pageContainer) pageContainer.classList.add("detail-mode");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setDetailAiCleanupStatus(nextState, message = "") {
  detailAiCleanupState = nextState;
  if (!detailAiCleanupStatusEl) return;
  const textByState = {
    idle: "",
    running: "AI Cleanup running...",
    success: message || "AI Cleanup complete.",
    failed: message || "AI Cleanup failed."
  };
  const text = textByState[nextState] || "";
  detailAiCleanupStatusEl.textContent = text;
  detailAiCleanupStatusEl.classList.toggle("hidden", !text);
  detailAiCleanupStatusEl.classList.toggle("detail-ai-cleanup-success", nextState === "success");
  detailAiCleanupStatusEl.classList.toggle("detail-ai-cleanup-failed", nextState === "failed");
}

async function runDetailAiCleanup() {
  const recipe = formState.selectedRecipe;
  if (!recipe?.id || !detailAiCleanupButton) return;
  if (detailAiCleanupState === "running") return;

  detailAiCleanupButton.disabled = true;
  detailAiCleanupButton.textContent = "Running...";
  setDetailAiCleanupStatus("running");

  try {
    const response = await apiFetch(`${API_BASE}/recipes/${encodeURIComponent(String(recipe.id))}/ai-cleanup`, {
      method: "POST"
    });
    if (!response.ok) {
      let errorText = "AI Cleanup failed.";
      try {
        const payload = await response.json();
        if (payload?.detail) errorText = String(payload.detail);
      } catch (_error) {
        // Keep fallback error text.
      }
      throw new Error(errorText);
    }
    const payload = await response.json();
    const cleanedPreview = payload?.preview && typeof payload.preview === "object" ? payload.preview : null;
    if (!cleanedPreview) {
      throw new Error("AI Cleanup returned an invalid preview.");
    }
    if (payload?.no_changes) {
      setDetailAiCleanupStatus("success", String(payload?.message || "No meaningful improvements recommended."));
      return;
    }
    const { hasIngredients, hasInstructions } = hasParsedCoreContent(cleanedPreview);
    if (!hasIngredients || !hasInstructions) {
      throw new Error("AI Cleanup returned an incomplete preview.");
    }
    const review = buildAiCleanupReviewChanges(recipe, cleanedPreview);
    if (!review.changes.length) {
      setDetailAiCleanupStatus("success", "No meaningful improvements recommended.");
      return;
    }
    showAiCleanupReview(review);
    setDetailAiCleanupStatus("success", "AI Cleanup ready to review.");
  } catch (error) {
    setDetailAiCleanupStatus("failed", error?.message || "AI Cleanup failed.");
  } finally {
    if (detailAiCleanupButton) {
      detailAiCleanupButton.disabled = false;
      detailAiCleanupButton.textContent = "AI Cleanup";
    }
  }
}

function cancelAiCleanupReview() {
  hideAiCleanupReview();
  setDetailAiCleanupStatus("success", "AI Cleanup canceled. Recipe unchanged.");
}

async function acceptAiCleanupReview() {
  if (!pendingAiCleanupReview?.recipeId || !pendingAiCleanupReview?.draftRecipe) return;
  if (!acceptAiCleanupReviewButton || !cancelAiCleanupReviewButton) return;

  const buttonLabel = acceptAiCleanupReviewButton.textContent || "Apply changes";
  acceptAiCleanupReviewButton.disabled = true;
  cancelAiCleanupReviewButton.disabled = true;
  if (closeAiCleanupReviewButton) closeAiCleanupReviewButton.disabled = true;
  acceptAiCleanupReviewButton.textContent = "Applying...";
  setAiCleanupReviewStatus("Applying AI cleanup changes...", "info");

  try {
    const reviewRecipeId = pendingAiCleanupReview.recipeId;
    const payload = buildRecipeSavePayloadFromRecipe(pendingAiCleanupReview.draftRecipe);
    const saveResult = await saveRecipePayload(payload, reviewRecipeId);
    if (!saveResult.ok) {
      throw new Error(saveResult.errorMessage);
    }

    hideAiCleanupReview();
    setDetailAiCleanupStatus("success", "AI Cleanup changes applied.");
    showStatus("Recipe saved.");

    await loadRecipes();
    const refreshed = allRecipes.find((item) => String(item.id) === reviewRecipeId);
    if (refreshed) {
      formState.selectedRecipe = refreshed;
      showRecipeDetail(refreshed);
    }
    setDetailAiCleanupStatus("success", "AI Cleanup changes applied.");
  } catch (error) {
    setAiCleanupReviewStatus(error?.message || "Unable to apply AI cleanup changes.", "error");
    setDetailAiCleanupStatus("failed", error?.message || "Unable to apply AI cleanup changes.");
  } finally {
    acceptAiCleanupReviewButton.disabled = false;
    cancelAiCleanupReviewButton.disabled = false;
    if (closeAiCleanupReviewButton) closeAiCleanupReviewButton.disabled = false;
    acceptAiCleanupReviewButton.textContent = buttonLabel;
  }
}

function hideRecipeDetail(shouldApplyFilters = true) {
  stopReviewStatusPolling();
  hideAiCleanupReview();
  if (!recipeDetailView) return;
  recipeDetailView.classList.add("hidden");
  closeDetailActionsMenu();
  closeDetailConvertMenu();
  toggleDetailCookbookPopover(false);
  if (currentView === "cookbook") {
    if (recipesContainer) recipesContainer.classList.remove("hidden");
    if (recipesListHeader) recipesListHeader.classList.remove("hidden");
  }
  if (pageContainer) pageContainer.classList.remove("detail-mode");
  if (shouldApplyFilters) applyRecipeFilters();
  formState.selectedRecipe = null;
  currentDetailRecipeId = "";
}

async function copyIngredients() {
  if (!copyIngredientsButton || !detailIngredientsEl) return;

  const ingredientLines = Array.from(detailIngredientsEl.querySelectorAll("li"))
    .map((item) => item.textContent?.trim() || "")
    .filter((item) => item && !item.toLowerCase().startsWith("no ingredients available"));
  if (!ingredientLines.length) return;

  const ingredientText = ingredientLines.join("\n");

  try {
    await writeToClipboard(ingredientText);
    showStatus("Ingredients copied.");
    if (statusMessage) {
      statusMessage.classList.add("success");
      statusMessage.classList.remove("error", "info");
    }
  } catch (error) {
    console.log("copy ingredients failed", error);
    showStatus("Could not copy ingredients.");
    if (statusMessage) {
      statusMessage.classList.add("error");
      statusMessage.classList.remove("success", "info");
    }
  }
}

async function writeToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "fixed";
  textArea.style.opacity = "0";
  textArea.style.pointerEvents = "none";
  document.body.appendChild(textArea);
  textArea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textArea);
  if (!copied) {
    throw new Error("Clipboard copy command failed");
  }
}



function formatRecipeForShare(recipe) {
  if (!recipe) return "";
  const lines = [];
  const title = String(recipe.title || "").trim() || "Untitled recipe";
  lines.push(title, "");
  const prep = normalizeTimeLabel(recipe.prep_time || recipe.prepTime || "");
  const cook = normalizeTimeLabel(recipe.cook_time || recipe.cookTime || "");
  const total = normalizeTimeLabel(recipe.total_time || recipe.totalTime || "");
  if (recipe.servings) lines.push(`Servings: ${recipe.servings}`);
  if (prep) lines.push(`Prep: ${prep}`);
  if (cook) lines.push(`Cook: ${cook}`);
  if (total) lines.push(`Total: ${total}`);
  if (lines[lines.length - 1] !== "") lines.push("");
  lines.push("Ingredients:");
  sanitizeIngredientGroups(recipe.ingredient_groups).forEach((group) => {
    if (group.title) lines.push(`${group.title}:`);
    group.items.forEach((item) => lines.push(`- ${item}`));
  });
  lines.push("", "Instructions:");
  let i = 1;
  sanitizeInstructionGroups(recipe.instruction_groups).forEach((group) => {
    if (group.title) lines.push(group.title);
    group.steps.forEach((step) => lines.push(`${i++}. ${step}`));
  });
  const sourceUrl = String(recipe.resolved_recipe_url || recipe.url || "").trim();
  if (sourceUrl) lines.push("", "Source:", sourceUrl);
  return lines.join("\n").trim();
}

function toggleShareModal(show) {
  if (!shareModal) return;
  shareModal.classList.toggle("hidden", !show);
  shareModal.setAttribute("aria-hidden", show ? "false" : "true");
}

async function copyRecipeText() {
  const formatted = formatRecipeForShare(formState.selectedRecipe);
  try {
    await writeToClipboard(formatted);
    showStatus("Recipe copied to clipboard.");
  } catch (_error) {
    window.prompt("Could not copy recipe. Copy manually:", formatted);
    showStatus("Could not copy recipe.");
  }
}

async function shareRecipeText() {
  const recipe = formState.selectedRecipe;
  const formatted = formatRecipeForShare(recipe);
  if (!formatted) return;
  try {
    if (navigator.share) {
      await navigator.share({ title: recipe.title || "Recipe", text: formatted });
    } else {
      await writeToClipboard(formatted);
      showStatus("Recipe copied to clipboard.");
    }
  } catch (_error) {
    showStatus("Could not share recipe.");
  }
}

function printRecipe() {
  const recipe = formState.selectedRecipe;
  if (!recipe) return;

  showStatus("Opening print view…");
  toggleShareModal(false);

  const originalContent = document.body.innerHTML;
  const escapedTitle = escapeHtml(recipe.title || "Untitled recipe");

  const prep = normalizeTimeLabel(recipe.prep_time || recipe.prepTime || "");
  const cook = normalizeTimeLabel(recipe.cook_time || recipe.cookTime || "");
  const total = normalizeTimeLabel(recipe.total_time || recipe.totalTime || "");
  const image = getRecipeImage(recipe);
  const sourceUrl = String(recipe.resolved_recipe_url || recipe.url || "").trim();
  const servings = normalizeServingsDisplay(recipe.servings || "");
  const ingredientGroups = sanitizeIngredientGroups(recipe.ingredient_groups);
  const ignoredInstructionSteps = new Set(["instructions", "instruction", "directions", "steps"]);
  const instructionGroups = sanitizeInstructionGroups(recipe.instruction_groups)
    .map((group) => {
      const title = String(group?.title || "").trim();
      const steps = Array.isArray(group?.steps)
        ? group.steps
            .map((step) => String(step || "").trim())
            .filter((step) => step && !ignoredInstructionSteps.has(step.toLowerCase()))
        : [];
      return { title, steps };
    })
    .filter((group) => group.steps.length > 0);

  const ingredientsHtml = ingredientGroups
    .map((group) => {
      const title = String(group?.title || "").trim();
      const items = Array.isArray(group?.items)
        ? group.items.map((item) => String(item || "").trim()).filter(Boolean)
        : [];
      if (!items.length) return "";
      const heading = title ? `<li><strong>${escapeHtml(title)}</strong></li>` : "";
      const itemsMarkup = items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
      return `${heading}${itemsMarkup}`;
    })
    .filter(Boolean)
    .join("");

  const instructionsHtml = instructionGroups
    .map((group) => {
      const title = String(group?.title || "").trim();
      const steps = Array.isArray(group?.steps) ? group.steps : [];
      if (!steps.length) return "";
      const heading = title ? `<li><strong>${escapeHtml(title)}</strong></li>` : "";
      const stepsMarkup = steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("");
      return `${heading}${stepsMarkup}`;
    })
    .filter(Boolean)
    .join("");

  const printHTML = `
    <h1>${escapedTitle}</h1>
    ${image ? `<img src="${escapeHtml(image)}" alt="Recipe image" />` : ""}
    ${servings ? `<p><strong>Servings:</strong> ${escapeHtml(servings)}</p>` : ""}
    ${prep ? `<p><strong>Prep:</strong> ${escapeHtml(prep)}</p>` : ""}
    ${cook ? `<p><strong>Cook:</strong> ${escapeHtml(cook)}</p>` : ""}
    ${total ? `<p><strong>Total:</strong> ${escapeHtml(total)}</p>` : ""}
    ${ingredientsHtml ? `<h2>Ingredients</h2><ul>${ingredientsHtml}</ul>` : ""}
    ${instructionsHtml ? `<h2>Instructions</h2><ol>${instructionsHtml}</ol>` : ""}
    ${sourceUrl ? `<p><strong>Source:</strong> ${escapeHtml(sourceUrl)}</p>` : ""}
  `;

  document.body.innerHTML = `
  <html>
    <head>
      <title>${escapedTitle}</title>
      <style>
        body {
          font-family: Arial, sans-serif;
          padding: 24px;
          color: #000;
        }
        img {
          max-width: 260px;
          display: block;
          margin-bottom: 16px;
        }
        h1 { margin-bottom: 16px; }
        h2 { margin-top: 24px; }
        ul, ol { margin-left: 20px; }
      </style>
    </head>
    <body>
      ${printHTML}
    </body>
  </html>
`;

  let restored = false;
  const restorePage = () => {
    if (restored) return;
    restored = true;
    document.body.innerHTML = originalContent;
    window.location.reload();
  };

  window.addEventListener("afterprint", restorePage, { once: true });

  window.setTimeout(() => {
    window.print();
  }, 50);

  window.setTimeout(restorePage, 3000);
}


async function deleteSelectedRecipe() {
  const recipe = formState.selectedRecipe;
  if (!recipe?.id) return;

  const shouldDelete = window.confirm(`Delete "${recipe.title || "this recipe"}"?`);
  if (!shouldDelete) return;

  await apiFetch(`${API_BASE}/recipes/${recipe.id}`, { method: "DELETE" });
  hideRecipeDetail();
  await loadRecipes();
}

async function saveDetailCookbookMembership() {
  const recipe = formState.selectedRecipe;
  if (!recipe?.id || !detailCookbookOptions) return;
  const membershipEndpoint = `${API_BASE}/recipes/${encodeURIComponent(String(recipe.id))}/cookbooks`;

  const selectedValues = Array.from(
    detailCookbookOptions.querySelectorAll("input[name=\"detail-cookbook-choice\"]:checked")
  ).map((input) => String(input.value || "").trim());

  const selectedIds = selectedValues
    .filter((value) => value !== UNCATEGORIZED_COOKBOOK_ID)
    .map((value) => Number(value))
    .filter(Number.isFinite);

  const saveResponse = await apiFetch(membershipEndpoint, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cookbook_ids: selectedIds })
  });
  if (!saveResponse.ok) {
    console.warn("[cookbook-membership] save failed", {
      recipeId: recipe.id,
      status: saveResponse.status
    });
    window.alert("Could not save cookbook membership. Please try again.");
    return;
  }

  const verifyResponse = await apiFetch(membershipEndpoint);
  if (!verifyResponse.ok) {
    console.warn("[cookbook-membership] verification fetch failed", {
      recipeId: recipe.id,
      status: verifyResponse.status
    });
  } else {
    const persistedCookbooks = await verifyResponse.json();
    const persistedIds = persistedCookbooks.map((item) => Number(item.id)).filter(Number.isFinite);
    updateRecipeInMemory(recipe.id, {
      cookbooks: persistedCookbooks,
      cookbook_ids: persistedIds
    });
  }

  await loadRecipes();
  const refreshed = allRecipes.find((item) => String(item.id) === String(recipe.id));
  if (refreshed) {
    formState.selectedRecipe = refreshed;
    renderDetailCookbookMembership(refreshed);
  }
  toggleDetailCookbookPopover(false);
}

function getDetailCookbookSelectionFromUi() {
  if (!detailCookbookOptions) return new Set();
  return new Set(
    Array.from(detailCookbookOptions.querySelectorAll("input[name=\"detail-cookbook-choice\"]:checked"))
      .map((input) => String(input.value || "").trim())
      .filter(Boolean)
  );
}

function updateShoppingSelectionControls() {
  const count = selectedShoppingRecipeIds.size;
  const visibleRecipes = getVisibleCookbookRecipes();
  const visibleCount = visibleRecipes.length;
  const allVisibleSelected = areAllVisibleRecipesSelected(visibleRecipes);
  if (shoppingSelectionToggle) {
    shoppingSelectionToggle.textContent = shoppingSelectionMode ? "Cancel selection" : "Select recipes";
  }
  if (selectAllRecipesButton) {
    selectAllRecipesButton.classList.toggle("hidden", !shoppingSelectionMode);
    selectAllRecipesButton.disabled = visibleCount === 0;
    selectAllRecipesButton.textContent = allVisibleSelected ? "Clear Selection" : "Select All";
  }
  if (shoppingSelectionCount) {
    const recipeLabel = count === 1 ? "recipe" : "recipes";
    shoppingSelectionCount.classList.toggle("hidden", !shoppingSelectionMode);
    shoppingSelectionCount.textContent = `${count} ${recipeLabel} selected`;
  }
  if (generateShoppingListButton) {
    generateShoppingListButton.classList.toggle("hidden", !shoppingSelectionMode);
    generateShoppingListButton.disabled = count === 0;
    generateShoppingListButton.textContent = count ? `Add to grocery list (${count})` : "Add to grocery list";
  }
  if (moveSelectedRecipesButton) {
    moveSelectedRecipesButton.classList.toggle("hidden", !shoppingSelectionMode);
    moveSelectedRecipesButton.disabled = count === 0;
  }
  if (deleteSelectedRecipesButton) {
    deleteSelectedRecipesButton.classList.toggle("hidden", !shoppingSelectionMode);
    deleteSelectedRecipesButton.disabled = count === 0;
  }
}

function resetShoppingSelection() {
  shoppingSelectionMode = false;
  selectedShoppingRecipeIds.clear();
  updateShoppingSelectionControls();
}

function hideShoppingListView() {
  if (shoppingListView) shoppingListView.classList.add("hidden");
}

function setGroceryListView() {
  currentView = "grocery";
  selectedCookbook = "";
  resetShoppingSelection();
  if (shoppingListView) shoppingListView.classList.remove("hidden");
  if (recipesContainer) recipesContainer.classList.add("hidden");
  if (recipesListHeader) recipesListHeader.classList.add("hidden");
  if (recipeDetailView) recipeDetailView.classList.add("hidden");
  if (dashboardMainPanel) dashboardMainPanel.classList.add("hidden");
  if (cookbooksPanel) cookbooksPanel.classList.add("hidden");
  if (dashboardSearchPanel) dashboardSearchPanel.classList.add("hidden");
  if (cookbookView) cookbookView.classList.remove("hidden");
  if (mealPlanView) mealPlanView.classList.add("hidden");
  if (adminUsersPanel) adminUsersPanel.classList.add("hidden");
  if (pageContainer) pageContainer.classList.remove("detail-mode");
  updateSidePanelActiveState();
}

function getRecipeById(recipeId) {
  return allRecipes.find((recipe) => String(recipe.id) === String(recipeId));
}

function getPreviewItemSource(item) {
  return Array.isArray(item?.items)
    ? item.items.find((entry) => entry?.recipe_id)
    : null;
}

function applyGroceryPreviewDisplayMode(items) {
  return (Array.isArray(items) ? items : []).map((item) => {
    const source = getPreviewItemSource(item);
    const recipe = source?.recipe_id ? getRecipeById(source.recipe_id) : null;
    const sourceText = String(item?.display_text || source?.display_text || source?.raw || item?.name || "").trim();
    if (!recipe || !sourceText) return item;
    return {
      ...item,
      display_text: formatIngredientLine(sourceText, getRecipeIngredientDisplayState(recipe))
    };
  });
}

function renderShoppingList(payload = {}) {
  const activeItems = Array.isArray(payload.active_items) ? payload.active_items : [];
  const checkedItems = Array.isArray(payload.checked_items) ? payload.checked_items : [];
  const sources = Array.isArray(payload.sources) ? payload.sources : [];
  if (shoppingListCount) {
    shoppingListCount.textContent = `${activeItems.length} active item${activeItems.length === 1 ? "" : "s"}`;
  }
  if (shoppingListItems) {
    const emptyText = !checkedItems.length
      ? "No grocery items yet. Add ingredients from a recipe."
      : "No active grocery items.";
    shoppingListItems.innerHTML = activeItems.map((item) => `
      <li class="shopping-list-item">
        <label>
          <input type="checkbox" data-grocery-item-id="${item.id}" ${item.checked ? "checked" : ""} />
          <span>${escapeHtml(item.display_text || item.name || "")}</span>
        </label>
      </li>
    `).join("") || `<li class="detail-empty-item">${escapeHtml(emptyText)}</li>`;
  }
  if (checkedGrocerySection) checkedGrocerySection.classList.toggle("hidden", !checkedItems.length);
  if (checkedGroceryCount) checkedGroceryCount.textContent = `${checkedItems.length} item${checkedItems.length === 1 ? "" : "s"}`;
  if (checkedGroceryItems) {
    checkedGroceryItems.innerHTML = checkedItems.map((item) => `
      <li class="shopping-list-item grocery-item-checked">
        <label>
          <input type="checkbox" data-grocery-item-id="${item.id}" checked />
          <span>${escapeHtml(item.display_text || item.name || "")}</span>
        </label>
      </li>
    `).join("");
  }
  if (grocerySourceCards) {
    grocerySourceCards.innerHTML = sources.map((source) => `
      <div class="grocery-source-card">
        <button type="button" class="grocery-source-link" data-grocery-source-open="${source.id}">${escapeHtml(source.title || "Recipe")}</button>
        <button type="button" class="grocery-source-remove" data-grocery-source-remove="${source.id}" aria-label="Remove ${escapeHtml(source.title || "recipe")}">×</button>
      </div>
    `).join("");
    grocerySourceCards.classList.toggle("hidden", activeItems.length + checkedItems.length === 0 || sources.length === 0);
  }
  if (clearGroceryListButton) clearGroceryListButton.classList.toggle("hidden", activeItems.length + checkedItems.length === 0);
}

async function loadGroceryList({ show = false } = {}) {
  const response = await apiFetch(`${API_BASE}/grocery-list`);
  if (!response.ok) throw new Error("Grocery list request failed");
  const payload = await response.json();
  renderShoppingList(payload);
  if (show) setGroceryListView();
}

function setMealPlanView() {
  currentView = "meal-plan";
  if (mealPlanView) mealPlanView.classList.remove("hidden");
  if (cookbookView) cookbookView.classList.add("hidden");
  if (shoppingListView) shoppingListView.classList.add("hidden");
  if (recipeDetailView) recipeDetailView.classList.add("hidden");
  if (recipesContainer) recipesContainer.classList.add("hidden");
  if (recipesListHeader) recipesListHeader.classList.add("hidden");
  if (dashboardMainPanel) dashboardMainPanel.classList.add("hidden");
  if (cookbooksPanel) cookbooksPanel.classList.add("hidden");
  if (dashboardSearchPanel) dashboardSearchPanel.classList.add("hidden");
  if (adminUsersPanel) adminUsersPanel.classList.add("hidden");
  updateSidePanelActiveState();
}

async function loadMealPlanWeek() {
  const startDate = formatIsoDate(mealPlanStartDate);
  if (mealPlanDays) mealPlanDays.innerHTML = "<p>Loading…</p>";
  const response = await apiFetch(`${API_BASE}/meal-plan?start_date=${encodeURIComponent(startDate)}`);
  if (!response.ok) {
    if (mealPlanStatus) {
      mealPlanStatus.textContent = "Could not load meal plan. Try again.";
      mealPlanStatus.classList.remove("hidden");
    }
    if (mealPlanDays) mealPlanDays.innerHTML = "";
    return;
  }
  const payload = await response.json();
  const days = Array.isArray(payload?.days) ? payload.days : [];
  if (mealPlanStatus) mealPlanStatus.classList.add("hidden");
  if (mealPlanWeekRange) mealPlanWeekRange.textContent = formatWeekRange(String(payload?.start_date || ""), String(payload?.end_date || ""));
  if (mealPlanDays) {
    mealPlanDays.innerHTML = days.map((day) => {
      const dayItems = Array.isArray(day?.items) ? day.items : [];
      const isToday = formatIsoDate(new Date()) === String(day?.date || "");
      const dayLabel = formatMealPlanDayLabel(String(day?.date || "")) || String(day?.label || "");
      const heading = isToday ? `Today • ${dayLabel}` : dayLabel;
      return `<article class="grocery-source-card meal-plan-day-card"><div class="meal-plan-day-header"><strong class="meal-plan-day-title">${escapeHtml(heading)}</strong><button class="secondary-button meal-plan-add-button" data-meal-plan-add="${escapeHtml(day?.date || "")}" type="button" aria-label="Add recipe">＋</button></div><div class="meal-plan-day-items">${dayItems.map((item) => `<div class="meal-plan-item-row" data-recipe-open="${item?.recipe_id ?? ""}"><div class="meal-plan-item-main">${item?.recipe_image_url ? `<img class="meal-plan-item-thumb" src="${escapeHtml(item.recipe_image_url)}" alt="">` : "<div class=\"meal-plan-item-thumb meal-plan-item-thumb-placeholder\" aria-hidden=\"true\"></div>"}<div class="meal-plan-item-text"><span class="meal-plan-item-title">${escapeHtml(item?.recipe_title || "Recipe")}</span><span class="meal-plan-slot-badge" data-slot="${escapeHtml(String(item?.meal_slot || "dinner").toLowerCase())}">${escapeHtml(formatMealSlotLabel(item?.meal_slot))}</span>${item?.servings_override ? `<span class="meal-plan-servings-note">Servings: ${escapeHtml(String(item.servings_override))}</span>` : ""}</div></div><button class="grocery-source-remove meal-plan-remove-button" data-meal-plan-remove="${item?.id ?? ""}" type="button" aria-label="Remove planned recipe">×</button></div>`).join("") || "<p class='grocery-empty'>No recipes yet</p>"}</div></article>`;
    }).join("");
  }
}

function showGroceryPreview(items) {
  pendingGroceryPreviewItems = Array.isArray(items) ? items : [];
  const multipleSources = new Set(
    pendingGroceryPreviewItems
      .map((item) => getPreviewItemSource(item)?.recipe_id)
      .filter((value) => value !== null && value !== undefined)
  ).size > 1;
  if (groceryPreviewItems) {
    groceryPreviewItems.innerHTML = pendingGroceryPreviewItems.map((item, index) => `
      <label class="grocery-preview-item">
        <input type="checkbox" data-grocery-preview-index="${index}" checked />
        <span>${escapeHtml(item.display_text || item.name || "")}</span>
        ${multipleSources ? `<small class="grocery-preview-source">${escapeHtml(getPreviewItemSource(item)?.recipe_title || "Recipe")}</small>` : ""}
      </label>
    `).join("") || "<p class=\"add-recipe-helper-text\">No ingredients found.</p>";
  }
  updateGroceryPreviewSelectionState();
  if (groceryPreviewStatus) groceryPreviewStatus.classList.add("hidden");
  if (groceryPreviewModal) {
    groceryPreviewModal.classList.remove("hidden");
    groceryPreviewModal.setAttribute("aria-hidden", "false");
  }
}

function updateGroceryPreviewSelectionState() {
  if (!confirmGroceryPreviewButton) return;
  const selectedCount = Array.from(groceryPreviewItems?.querySelectorAll("[data-grocery-preview-index]:checked") || []).length;
  confirmGroceryPreviewButton.disabled = selectedCount === 0;
  confirmGroceryPreviewButton.textContent = selectedCount > 0 ? `Add ${selectedCount} item${selectedCount === 1 ? "" : "s"}` : "Add items";
}

function hideGroceryPreview() {
  if (!groceryPreviewModal) return;
  groceryPreviewModal.classList.add("hidden");
  groceryPreviewModal.setAttribute("aria-hidden", "true");
}

async function openGroceryPreviewForRecipeIds(recipeIds) {
  const normalizedRecipeIds = Array.from(new Set((recipeIds || []).map(Number).filter(Number.isFinite)));
  if (!normalizedRecipeIds.length) return;
  const response = await apiFetch(`${API_BASE}/grocery-list/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipe_ids: normalizedRecipeIds })
  });
  if (!response.ok) throw new Error("Grocery preview request failed");
  const payload = await response.json();
  showGroceryPreview(applyGroceryPreviewDisplayMode(payload.items || []));
}

async function generateShoppingList() {
  const recipeIds = Array.from(selectedShoppingRecipeIds).map((id) => Number(id)).filter(Number.isFinite);
  if (!recipeIds.length) return;
  if (generateShoppingListButton) generateShoppingListButton.disabled = true;
  try {
    await openGroceryPreviewForRecipeIds(recipeIds);
  } catch (error) {
    if (shoppingListStatus) {
      shoppingListStatus.textContent = "Could not prepare grocery preview.";
      shoppingListStatus.classList.remove("hidden");
    }
  } finally {
    updateShoppingSelectionControls();
  }
}

async function ensureCookbookExistsByName(name) {
  const normalizedName = String(name || "").trim();
  if (!normalizedName || normalizedName.toLowerCase() === "uncategorized") return null;

  const existingCookbook = allCookbooks.find(
    (cookbook) => String(cookbook?.name || "").trim().toLowerCase() === normalizedName.toLowerCase()
  );
  if (existingCookbook) return existingCookbook;

  const response = await apiFetch(`${API_BASE}/cookbooks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: normalizedName })
  });
  if (!response.ok) throw new Error("Could not create cookbook.");
  return response.json();
}

async function moveSelectedRecipesToCookbook() {
  const recipeIds = Array.from(selectedShoppingRecipeIds);
  if (!recipeIds.length) return;

  const alternativeCookbooks = allCookbooks.filter(
    (cookbook) => String(cookbook?.name || "").trim().toLowerCase() !== String(selectedCookbook || "").trim().toLowerCase()
  );
  const defaultDestination = alternativeCookbooks[0]?.name || "";
  const destinationName = alternativeCookbooks.length === 1
    ? defaultDestination
    : window.prompt(
      `Move ${recipeIds.length} selected recipe${recipeIds.length === 1 ? "" : "s"} to cookbook:`,
      defaultDestination
    );
  const normalizedDestinationName = String(destinationName || "").trim();
  if (!normalizedDestinationName) return;
  if (normalizedDestinationName.toLowerCase() === String(selectedCookbook || "").trim().toLowerCase()) return;

  const destinationCookbook = normalizedDestinationName.toLowerCase() === "uncategorized"
    ? null
    : await ensureCookbookExistsByName(normalizedDestinationName);
  const currentCookbook = allCookbooks.find(
    (cookbook) => String(cookbook?.name || "").trim().toLowerCase() === String(selectedCookbook || "").trim().toLowerCase()
  );

  await Promise.all(recipeIds.map(async (recipeId) => {
    const recipe = allRecipes.find((entry) => String(entry?.id) === String(recipeId));
    if (!recipe) return;

    const nextCookbookIds = new Set(getRecipeCookbookIds(recipe));
    if (currentCookbook?.id !== null && currentCookbook?.id !== undefined) {
      nextCookbookIds.delete(Number(currentCookbook.id));
    }
    if (destinationCookbook?.id !== null && destinationCookbook?.id !== undefined) {
      nextCookbookIds.add(Number(destinationCookbook.id));
    }

    const response = await apiFetch(`${API_BASE}/recipes/${encodeURIComponent(String(recipeId))}/cookbooks`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cookbook_ids: Array.from(nextCookbookIds).sort((a, b) => a - b) })
    });
    if (!response.ok) throw new Error("Could not move selected recipes.");
  }));

  resetShoppingSelection();
  await loadRecipes();
}

function renderRecipes(recipes, container = recipesContainer) {
  if (!container) return;

  container.innerHTML = recipes
    .map((recipe) => {
      const safeTitle = escapeHtml(recipe.title || "Untitled recipe");

      const imageUrl = getRecipeImage(recipe);
      const hasImage = Boolean(imageUrl);
      const imageMarkup = `
        <img class="recipe-card-image ${hasImage ? "" : "hidden"}" src="${hasImage ? escapeHtml(imageUrl) : ""}" alt="${safeTitle} image" loading="lazy" />
        <div class="recipe-card-placeholder ${hasImage ? "hidden" : ""}" aria-hidden="true"><span class="recipe-card-placeholder-icon">🍽</span></div>
      `;
      const prepTime = String(recipe.prep_time || "").trim();
      const cookTime = String(recipe.cook_time || "").trim();
      const metadataItems = [
        prepTime ? `<span class="recipe-card-meta-item">Prep ${escapeHtml(prepTime)}</span>` : "",
        cookTime ? `<span class="recipe-card-meta-item">Cook ${escapeHtml(cookTime)}</span>` : ""
      ].filter(Boolean);
      const metadataMarkup = metadataItems.length
        ? `<div class="recipe-card-meta">${metadataItems.join("")}</div>`
        : "";
      return `
        <article class="recipe-card-tile recipe-card" data-card-open-id="${recipe.id}" role="button" tabindex="0" aria-label="Open ${safeTitle}">
          <label class="recipe-select-checkbox ${shoppingSelectionMode ? "" : "hidden"}" aria-label="Select ${safeTitle}">
            <input type="checkbox" data-shopping-recipe-id="${recipe.id}" ${selectedShoppingRecipeIds.has(String(recipe.id)) ? "checked" : ""} />
          </label>
          <div class="recipe-card-media">
            ${imageMarkup}
            <span class="card-media-overlay" aria-hidden="true"></span>
          </div>
          <div class="recipe-card-content">
            <h3 class="recipe-card-title" title="${safeTitle}">${safeTitle}</h3>
            ${metadataMarkup}
          </div>
        </article>
      `;
    })
    .join("");

  container.querySelectorAll("[data-card-open-id]").forEach((card) => {
    card.addEventListener("click", () => {
      if (shoppingSelectionMode) return;
      const recipe = recipes.find((entry) => String(entry.id) === card.dataset.cardOpenId);
      if (recipe) openRecipe(recipe);
    });

    card.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      if (shoppingSelectionMode) return;
      const recipe = recipes.find((entry) => String(entry.id) === card.dataset.cardOpenId);
      if (recipe) openRecipe(recipe);
    });
  });

  container.querySelectorAll("[data-shopping-recipe-id]").forEach((input) => {
    input.addEventListener("click", (event) => event.stopPropagation());
    input.addEventListener("change", () => {
      const recipeId = String(input.dataset.shoppingRecipeId || "").trim();
      if (!recipeId) return;
      if (input.checked) selectedShoppingRecipeIds.add(recipeId);
      else selectedShoppingRecipeIds.delete(recipeId);
      updateShoppingSelectionControls();
    });
  });

  container.querySelectorAll(".recipe-card-image").forEach((imageEl) => {
    imageEl.addEventListener("error", () => {
      imageEl.classList.add("hidden");
      const media = imageEl.closest(".recipe-card-media");
      const placeholder = media?.querySelector(".recipe-card-placeholder");
      if (placeholder) placeholder.classList.remove("hidden");
    });
  });

}

function debounce(fn, wait = 180) {
  let timeoutId;
  return (...args) => {
    window.clearTimeout(timeoutId);
    timeoutId = window.setTimeout(() => fn(...args), wait);
  };
}

async function loadRecipes() {
  const [recipesRes, cookbooksRes] = await Promise.all([
    apiFetch(`${API_BASE}/recipes`),
    apiFetch(`${API_BASE}/cookbooks`)
  ]);
  if (!recipesRes.ok || !cookbooksRes.ok) return;
  allRecipes = await recipesRes.json();
  allCookbooks = await cookbooksRes.json();
  applyRecipeFilters();
}

async function openImportedRecipeAndNotify(recipeId, fallbackState, statusText) {
  const normalizedRecipeId = String(recipeId || "").trim();
  if (!normalizedRecipeId) {
    setShareImportState(fallbackState);
    return;
  }

  const matchingRecipe = allRecipes.find((recipe) => String(recipe.id) === normalizedRecipeId);
  if (!matchingRecipe) {
    setShareImportState(fallbackState);
    return;
  }

  setShareImportState(null);
  openRecipe(matchingRecipe);

  if (statusText) {
    showStatus(statusText);
    if (statusMessage) {
      statusMessage.classList.add("success");
      statusMessage.classList.remove("error", "info");
    }
  }
}

async function autoImportPendingShare() {
  captureSharedPayloadFromQuery();

  const params = new URLSearchParams(window.location.search || "");
  const shareImportRequested = params.get("share_import") === "1" || params.get("share_target") === "1";
  const pendingShare = getPendingSharedPayload();

  if (!shareImportRequested && !pendingShare) {
    return false;
  }

  const sharedUrl = String(localStorage.getItem("shared_url") || pendingShare?.url || "").trim();
  const sharedText = String(localStorage.getItem("shared_text") || pendingShare?.text || "").trim();
  const sharedTitle = String(localStorage.getItem("shared_title") || pendingShare?.title || "").trim();
  const combinedShareText = [sharedUrl, sharedText, sharedTitle].filter(Boolean).join("\n");
  const extractedSharedUrl = extractUrlFromText(combinedShareText);
  console.info("pending share routing", {
    shareImportRequested,
    pendingShare,
    sharedUrl,
    sharedText,
    sharedTitle,
    extractedSharedUrl
  });

  clearEditMode();
  form?.reset();
  showAddRecipeModal();

  if (extractedSharedUrl) {
    applyAddRecipeMode("import");
    if (urlInput) {
      urlInput.value = extractedSharedUrl;
      urlInput.focus();
    }
    if (titleInput && !titleInput.value && sharedTitle) titleInput.value = sharedTitle;
  } else if (sharedText) {
    applyAddRecipeMode("paste");
    if (pasteRecipeTextInput) pasteRecipeTextInput.value = sharedText;
    if (titleInput && !titleInput.value && sharedTitle) titleInput.value = sharedTitle;
  } else {
    applyAddRecipeMode("import");
  }

  showAddRecipeStatus("Shared recipe content received. Review and import when ready.", "info");

  clearPendingSharedPayload();
  window.history.replaceState({}, document.title, window.location.pathname);
  return true;
}


async function tryClipboard() {
  if (!navigator.clipboard) return;

  try {
    const text = await navigator.clipboard.readText();
    const url = extractUrlFromText(text);

    if (url && !urlInput.value) {
      urlInput.value = url;
    }
  } catch (e) {
    console.log("clipboard blocked");
  }
}

async function initializeAuthenticatedApp() {
  await loadRecipes();
}

async function saveRecipePayload(payload, recipeId = "") {
  const normalizedRecipeId = String(recipeId || "").trim();
  const method = normalizedRecipeId ? "PUT" : "POST";
  const targetUrl = normalizedRecipeId
    ? `${API_BASE}/recipes/${normalizedRecipeId}`
    : `${API_BASE}/recipes`;

  const response = await apiFetch(targetUrl, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    let errorMessage = "Unable to save recipe. Please try again.";
    const errorText = await response.text();
    console.error("Save failed:", errorText);
    try {
      const data = JSON.parse(errorText);
      if (response.status === 422 && Array.isArray(data?.detail) && data.detail.length) {
        const firstIssue = data.detail[0];
        const issuePath = Array.isArray(firstIssue?.loc) ? firstIssue.loc.join(".") : "";
        const issueMessage = String(firstIssue?.msg || "Validation failed");
        errorMessage = `Validation failed${issuePath ? ` (${issuePath})` : ""}: ${issueMessage}`;
      } else if (data?.detail) {
        errorMessage = `Unable to save recipe: ${String(data.detail)}`;
      }
    } catch (_err) {
      // Keep fallback error message.
    }
    return { ok: false, errorMessage };
  }

  return { ok: true, savedRecipe: await response.json() };
}

submitButton?.addEventListener("click", async () => {
  if (isImportLoading) return;
  clearAddRecipeStatus();
  await enrichFromUrl();
});
uploadPhotoButton?.addEventListener("click", () => {
  if (isImportLoading) return;
  imageUploadInput?.click();
});
browserOptionButton?.addEventListener("click", () => {
  if (isImportLoading) return;
  clearAddRecipeStatus();
  applyAddRecipeMode("import");
  urlInput?.focus();
});
pasteTextOptionButton?.addEventListener("click", () => {
  if (isImportLoading) return;
  clearAddRecipeStatus();
  applyAddRecipeMode("paste");
  pasteRecipeTextInput?.focus();
});
importModeBackButton?.addEventListener("click", () => {
  if (isImportLoading) return;
  clearAddRecipeStatus();
  applyAddRecipeMode("choose");
});
pasteTextImportButton?.addEventListener("click", async () => {
  if (isImportLoading) return;
  const text = pasteRecipeTextInput?.value.trim() || "";
  if (!text) {
    showAddRecipeStatus("Paste recipe text first.");
    return;
  }
  isImportLoading = true;
  pasteTextImportButton.disabled = true;
  pasteTextImportButton.textContent = "Importing...";
  try {
    const response = await apiFetch(`${API_BASE}/import/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    if (!response.ok) {
      showAddRecipeStatus("Could not parse pasted recipe text.");
      return;
    }
    const data = await response.json();
    titleInput.value = normalizeImportedRecipeTitle(data.title);
    sourceAppInput.value = data.source_app || "Paste";
    sourceTypeInput.value = data.source_type || "Paste Text";
    formState.import_context = {
      original_url: "",
      resolved_url: "",
      original_source_url: "",
      resolved_recipe_url: "",
      content_source: "pasted_text"
    };
    applyParsedPreview(data);
    applyAddRecipeMode("paste", { parsed: true });
    renderParsedResults();
    clearAddRecipeStatus();
  } finally {
    isImportLoading = false;
    pasteTextImportButton.disabled = false;
    pasteTextImportButton.textContent = "Import pasted recipe";
  }
});
imageUploadInput?.addEventListener("change", async () => {
  const file = imageUploadInput.files?.[0];
  console.info("image upload input change fired", {
    filePresent: Boolean(file),
    filename: file?.name || "",
    size: Number(file?.size || 0),
    type: file?.type || ""
  });
  if (!file) return;
  await importFromImageFile(file);
  imageUploadInput.value = "";
});
editImageInput?.addEventListener("change", () => {
  const file = editImageInput.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    const imageValue = typeof reader.result === "string" ? reader.result : "";
    if (imageUrlInput) imageUrlInput.value = imageValue;
    formState.parsed.image_url = imageValue;
    renderEditImagePreview();
  });
  reader.readAsDataURL(file);
});

clearEditImageButton?.addEventListener("click", () => {
  if (imageUrlInput) imageUrlInput.value = "";
  if (editImageInput) editImageInput.value = "";
  formState.parsed.image_url = "";
  renderEditImagePreview();
});

urlInput?.addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  if (isImportLoading) return;
  clearAddRecipeStatus();
  await enrichFromUrl();
});

editTitleInput?.addEventListener("input", () => {
  if (!titleInput) return;
  titleInput.value = editTitleInput.value;
});

editServingsInput?.addEventListener("input", () => {
  formState.parsed.servings = editServingsInput.value;
});

editPrepTimeInput?.addEventListener("input", () => {
  formState.parsed.prep_time = editPrepTimeInput.value;
});

editCookTimeInput?.addEventListener("input", () => {
  formState.parsed.cook_time = editCookTimeInput.value;
});

parsedIngredientsEl?.addEventListener("input", (event) => {
  const input = event.target.closest("[data-ingredient-input]");
  if (!input) return;
  const index = Number(input.dataset.ingredientInput);
  if (!Number.isInteger(index)) return;
  const nextIngredients = getEditableIngredients();
  nextIngredients[index] = input.dataset.ingredientSection === "true"
    ? (input.value.trim() ? `# ${input.value.trim()}` : "")
    : input.value;
  syncParsedCollectionsFromEditable(nextIngredients, null);
});

parsedInstructionsEl?.addEventListener("input", (event) => {
  const input = event.target.closest("[data-instruction-input]");
  if (!input) return;
  const index = Number(input.dataset.instructionInput);
  if (!Number.isInteger(index)) return;
  const nextInstructions = getEditableInstructions();
  nextInstructions[index] = input.dataset.instructionSection === "true"
    ? (input.value.trim() ? `# ${input.value.trim()}` : "")
    : input.value;
  syncParsedCollectionsFromEditable(null, nextInstructions);
});

parsedIngredientsEl?.addEventListener("click", (event) => {
  const convertSectionButton = event.target.closest("[data-ingredient-convert-section]");
  if (convertSectionButton) {
    const index = Number(convertSectionButton.dataset.ingredientConvertSection);
    if (!Number.isInteger(index)) return;
    const nextIngredients = getEditableIngredients();
    const currentValue = String(nextIngredients[index] ?? "");
    const isSection = /^#\s*\S/.test(currentValue.trim());
    const normalized = isSection
      ? currentValue.replace(/^#\s*/, "")
      : (currentValue.trim() ? `# ${currentValue.trim()}` : "");
    nextIngredients[index] = normalized;
    syncParsedCollectionsFromEditable(nextIngredients, null);
    renderParsedResults();
    return;
  }
  const deleteButton = event.target.closest("[data-ingredient-delete]");
  if (deleteButton) {
    const index = Number(deleteButton.dataset.ingredientDelete);
    const nextIngredients = getEditableIngredients().filter((_, itemIndex) => itemIndex !== index);
    syncParsedCollectionsFromEditable(nextIngredients, null);
    renderParsedResults();
    return;
  }
  const upButton = event.target.closest("[data-ingredient-up]");
  if (upButton) {
    const index = Number(upButton.dataset.ingredientUp);
    const nextIngredients = moveListItem(getEditableIngredients(), index, index - 1);
    syncParsedCollectionsFromEditable(nextIngredients, null);
    renderParsedResults();
    return;
  }
  const downButton = event.target.closest("[data-ingredient-down]");
  if (downButton) {
    const index = Number(downButton.dataset.ingredientDown);
    const nextIngredients = moveListItem(getEditableIngredients(), index, index + 1);
    syncParsedCollectionsFromEditable(nextIngredients, null);
    renderParsedResults();
  }
});

parsedInstructionsEl?.addEventListener("click", (event) => {
  const convertSectionButton = event.target.closest("[data-instruction-convert-section]");
  if (convertSectionButton) {
    const index = Number(convertSectionButton.dataset.instructionConvertSection);
    if (!Number.isInteger(index)) return;
    const nextInstructions = getEditableInstructions();
    const currentValue = String(nextInstructions[index] ?? "");
    const isSection = /^#\s*\S/.test(currentValue.trim());
    const normalized = isSection
      ? currentValue.replace(/^#\s*/, "")
      : (currentValue.trim() ? `# ${currentValue.trim()}` : "");
    nextInstructions[index] = normalized;
    syncParsedCollectionsFromEditable(null, nextInstructions);
    renderParsedResults();
    return;
  }
  const deleteButton = event.target.closest("[data-instruction-delete]");
  if (deleteButton) {
    const index = Number(deleteButton.dataset.instructionDelete);
    const nextInstructions = getEditableInstructions().filter((_, itemIndex) => itemIndex !== index);
    syncParsedCollectionsFromEditable(null, nextInstructions);
    renderParsedResults();
    return;
  }
  const upButton = event.target.closest("[data-instruction-up]");
  if (upButton) {
    const index = Number(upButton.dataset.instructionUp);
    const nextInstructions = moveListItem(getEditableInstructions(), index, index - 1);
    syncParsedCollectionsFromEditable(null, nextInstructions);
    renderParsedResults();
    return;
  }
  const downButton = event.target.closest("[data-instruction-down]");
  if (downButton) {
    const index = Number(downButton.dataset.instructionDown);
    const nextInstructions = moveListItem(getEditableInstructions(), index, index + 1);
    syncParsedCollectionsFromEditable(null, nextInstructions);
    renderParsedResults();
  }
});

addIngredientButton?.addEventListener("click", () => {
  const nextIngredients = [...getEditableIngredients(), ""];
  syncParsedCollectionsFromEditable(nextIngredients, null);
  pendingIngredientFocusIndex = nextIngredients.length - 1;
  renderParsedResults();
});

addIngredientSectionButton?.addEventListener("click", () => {
  const sectionName = window.prompt("Section name");
  if (!sectionName) return;
  const nextIngredients = [...getEditableIngredients(), `# ${sectionName.trim()}`, ""];
  syncParsedCollectionsFromEditable(nextIngredients, null);
  pendingIngredientFocusIndex = nextIngredients.length - 1;
  renderParsedResults();
});

addInstructionButton?.addEventListener("click", () => {
  const nextInstructions = [...getEditableInstructions(), ""];
  syncParsedCollectionsFromEditable(null, nextInstructions);
  pendingInstructionFocusIndex = nextInstructions.length - 1;
  renderParsedResults();
});

addInstructionSectionButton?.addEventListener("click", () => {
  const sectionName = window.prompt("Section name");
  if (!sectionName) return;
  const nextInstructions = [...getEditableInstructions(), `# ${sectionName.trim()}`, ""];
  syncParsedCollectionsFromEditable(null, nextInstructions);
  pendingInstructionFocusIndex = nextInstructions.length - 1;
  renderParsedResults();
});

ingredientsReorderButton?.addEventListener("click", () => {
  ingredientReorderMode = !ingredientReorderMode;
  renderParsedResults();
});

instructionsReorderButton?.addEventListener("click", () => {
  instructionReorderMode = !instructionReorderMode;
  renderParsedResults();
});

// submit
if (form) form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (isRecipeSaving) return;
  clearAddRecipeStatus();
  const titleDraft = (editTitleInput?.value ?? titleInput?.value ?? "").trim();
  const trimmedTitle = titleDraft;
  const resolvedTitle = trimmedTitle || inferTitleFromUrl(urlInput.value);
  const cleanedIngredients = getEditableIngredients()
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const cleanedInstructions = getEditableInstructions()
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  syncParsedCollectionsFromEditable(cleanedIngredients, cleanedInstructions);
  const cleanedIngredientGroups = sanitizeIngredientGroups(formState.parsed.ingredient_groups);
  const cleanedInstructionGroups = sanitizeInstructionGroups(formState.parsed.instruction_groups);
  const flatIngredients = cleanedIngredientGroups.length
    ? cleanedIngredientGroups.flatMap((group) => group.items)
    : cleanedIngredients;
  const flatInstructions = cleanedInstructionGroups.length
    ? cleanedInstructionGroups.flatMap((group) => group.steps)
    : cleanedInstructions;

  const needsReview = false;
  const reviewStatus = editIdInput?.value
    ? String(formState.selectedRecipe?.review_status || "none")
    : "none";

  const payload = {
    title: resolvedTitle,
    url: urlInput.value.trim(),
    original_source_url: (formState.import_context.original_source_url || "").trim() || null,
    resolved_recipe_url: (formState.import_context.resolved_recipe_url || urlInput.value || "").trim() || null,
    content_source: (formState.import_context.content_source || "direct_recipe_url").trim(),
    image_url: (imageUrlInput?.value || formState.parsed.image_url || "").trim(),
    source_app: (sourceAppInput?.value || "").trim() || "Chrome",
    source_type: (sourceTypeInput?.value || "").trim() || "Web",
    notes: notesInput.value,
    tags: tagsInput.value,
    needs_review: needsReview,
    review_status: reviewStatus,
    servings: ((editServingsInput?.value ?? formState.parsed.servings) || "").trim(),
    prep_time: ((editPrepTimeInput?.value ?? formState.parsed.prep_time) || "").trim(),
    cook_time: ((editCookTimeInput?.value ?? formState.parsed.cook_time) || "").trim(),
    total_time: formState.parsed.total_time || "",
    prep_minutes: formState.parsed.prep_minutes ?? null,
    cook_minutes: formState.parsed.cook_minutes ?? null,
    total_minutes: formState.parsed.total_minutes ?? null,
    ingredients: flatIngredients,
    instructions: flatInstructions,
    ingredient_groups: cleanedIngredientGroups,
    instruction_groups: cleanedInstructionGroups,
    ai_review_source_payload: formState.parsed.ai_review_source_payload || null
  };
  if (!String(payload.title || "").trim()) {
    showAddRecipeStatus("Title is required", "error");
    return;
  }
  if (!Array.isArray(payload.ingredients)) payload.ingredients = [];
  if (!Array.isArray(payload.instructions)) payload.instructions = [];
  if (addRecipeMode === "manual") {
    payload.source_type = "Manual";
    payload.source_app = "Manual";
    payload.content_source = "manual";
  }

  if (!payload.url) {
    payload.url = "";
    if (addRecipeMode === "manual") {
      payload.source_type = "Manual";
      payload.source_app = "Manual";
      payload.content_source = "manual";
    } else if (addRecipeMode === "paste") {
      payload.source_type = "Paste Text";
      payload.source_app = "Paste";
      payload.content_source = "pasted_text";
    } else {
      payload.source_type = "Image";
      payload.content_source = "image_ocr";
    }
    payload.original_source_url = null;
    payload.resolved_recipe_url = null;
  }

  const recipeId = editIdInput.value.trim();
  const isCreating = !recipeId;
  const { hasIngredients, hasInstructions } = hasParsedCoreContent(formState.parsed);
  if (
    isCreating &&
    formState.parsed.metadata_extracted &&
    payload.url &&
    !hasIngredients &&
    !hasInstructions
  ) {
    showAddRecipeStatus("Could not fully parse this recipe. Review before saving.");
    return;
  }

  const submitLabelBeforeSave = addRecipeSubmitButton?.textContent || "Save";

  isRecipeSaving = true;
  showAddRecipeStatus("Saving recipe...", "info");
  if (addRecipeSubmitButton) {
    addRecipeSubmitButton.disabled = true;
    addRecipeSubmitButton.textContent = "Saving...";
  }
  if (bottomSaveRecipeButton) {
    bottomSaveRecipeButton.disabled = true;
    bottomSaveRecipeButton.textContent = "Saving...";
  }
  try {
    if (addRecipeMode === "manual") {
      console.log("Saving manual recipe payload:", payload);
    }
    console.log("Submitting payload:", payload);
    const saveResult = await saveRecipePayload(payload, recipeId);
    if (!saveResult.ok) {
      showAddRecipeStatus(saveResult.errorMessage);
      return;
    }

    const savedRecipe = saveResult.savedRecipe;
    showStatus(recipeId ? "Recipe saved." : "Recipe added.");
    const savedRecipeId = String(savedRecipe?.id || recipeId || "").trim();
    const selectedRecipeId = String(formState.selectedRecipe?.id || "").trim();
    const shouldRefreshDetail = Boolean(savedRecipeId && selectedRecipeId && selectedRecipeId === savedRecipeId);

    form.reset();
    clearEditMode();
    clearAddRecipeStatus();
    hideAddRecipeModal();
    formState.selectedRecipe = null;
    currentDetailRecipeId = "";
    await loadRecipes();
    const refreshedRecipe = savedRecipeId
      ? allRecipes.find((item) => String(item.id) === savedRecipeId)
      : null;
    if (refreshedRecipe) {
      if (shouldRefreshDetail) showRecipeDetail(refreshedRecipe);
      formState.selectedRecipe = refreshedRecipe;
    }
  } catch (err) {
    console.error("Save exception:", err);
    showAddRecipeStatus("Unable to save recipe. Please try again.", "error");
  } finally {
    isRecipeSaving = false;
    if (addRecipeSubmitButton) {
      addRecipeSubmitButton.disabled = false;
      addRecipeSubmitButton.textContent = submitLabelBeforeSave;
    }
    if (bottomSaveRecipeButton) {
      renderParsedResults();
      bottomSaveRecipeButton.textContent = submitLabelBeforeSave;
    }
  }
});

if (cancelEditButton) {
  cancelEditButton.addEventListener("click", () => {
    form.reset();
    clearEditMode();
    hideAddRecipeModal();
  });
}

if (refreshButton) {
  refreshButton.addEventListener("click", loadRecipes);
}

if (runAiCleanupButton) {
  runAiCleanupButton.addEventListener("click", runModalAiCleanup);
}

if (searchInput) {
  const debouncedApplyRecipeFilters = debounce(applyRecipeFilters, 180);
  searchInput.addEventListener("input", debouncedApplyRecipeFilters);
  if (cookbookSearchInput) cookbookSearchInput.addEventListener("input", debouncedApplyRecipeFilters);
}

if (!searchInput && cookbookSearchInput) {
  cookbookSearchInput.addEventListener("input", debounce(applyRecipeFilters, 180));
}

if (backToCookbooksButton) {
  backToCookbooksButton.addEventListener("click", navigateToDashboardHome);
}

if (cookbookMenuButton) {
  cookbookMenuButton.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleCookbookActionsMenu();
  });
}

if (renameCookbookButton) {
  renameCookbookButton.addEventListener("click", async () => {
    closeCookbookActionsMenu();
    await renameCurrentCookbook();
  });
}

if (deleteCookbookButton) {
  deleteCookbookButton.addEventListener("click", async () => {
    closeCookbookActionsMenu();
    await deleteCurrentCookbook();
  });
}

document.addEventListener("click", (event) => {
  const mealPlanButton = event.target.closest("#detail-meal-plan-button");
  if (mealPlanButton) {
    event.preventDefault();
    event.stopPropagation();

    if (!mealPlanAddModal) {
      console.warn("Meal plan modal not found");
      return;
    }

    const selectedRecipe =
      (typeof getDetailRecipeSelection === "function" && getDetailRecipeSelection()) ||
      formState.selectedRecipe;

    const preferredRecipeId =
      selectedRecipe?.id || currentDetailRecipeId || "";

    console.log("Meal Plan button clicked", preferredRecipeId);

    openMealPlanAddModal({
      planDate: formatIsoDate(new Date()),
      preferredRecipeId
    });

    return;
  }

  if (cookbookActionsMenuOpen && cookbookActionsMenu && cookbookMenuButton) {
    const clickedInsideMenu = cookbookActionsMenu.contains(event.target);
    const clickedMenuButton = cookbookMenuButton.contains(event.target);
    if (!clickedInsideMenu && !clickedMenuButton) {
      closeCookbookActionsMenu();
    }
  }

  if (detailActionsMenuOpen && detailActionsMenu && detailMenuButton) {
    const clickedInsideMenu = detailActionsMenu.contains(event.target);
    const clickedMenuButton = detailMenuButton.contains(event.target);
    if (!clickedInsideMenu && !clickedMenuButton) {
      closeDetailActionsMenu();
    }
  }

  if (detailCookbookPopoverOpen && detailCookbookPopover && detailCookbookAddButton) {
    const clickedInsidePopover = detailCookbookPopover.contains(event.target);
    const clickedTriggerButton = detailCookbookAddButton.contains(event.target);
    if (!clickedInsidePopover && !clickedTriggerButton) {
      toggleDetailCookbookPopover(false);
    }
  }

  if (detailConvertMenuOpen && detailConvertMenu && detailConvertButton) {
    const clickedInsideMenu = detailConvertMenu.contains(event.target);
    const clickedConvertButton = detailConvertButton.contains(event.target);
    if (!clickedInsideMenu && !clickedConvertButton) {
      closeDetailConvertMenu();
    }
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && cookbookActionsMenuOpen) {
    closeCookbookActionsMenu();
  }
  if (event.key === "Escape" && detailActionsMenuOpen) {
    closeDetailActionsMenu();
  }
  if (event.key === "Escape" && detailCookbookPopoverOpen) {
    toggleDetailCookbookPopover(false);
  }
  if (event.key === "Escape" && detailConvertMenuOpen) {
    closeDetailConvertMenu();
  }
});

window.addEventListener("resize", () => {
  if (cookbookActionsMenuOpen) {
    positionCookbookActionsMenu();
  }
  if (window.matchMedia(MOBILE_SIDEBAR_MEDIA_QUERY).matches) {
    if (sidePanelExpanded) {
      setSidePanelExpanded(false, false);
    }
    return;
  }

  const desktopPreference = localStorage.getItem("recipe_clipper_sidebar_expanded");
  if (!sidePanelExpanded && desktopPreference === "true") {
    setSidePanelExpanded(true, false);
  }
});

if (navCookbooksButton) {
  navCookbooksButton.addEventListener("click", navigateToDashboardHome);
}

if (navAdminUsersButton) {
  navAdminUsersButton.addEventListener("click", async () => {
    setAdminUsersView();
    if (!currentUser?.is_admin) return;
    await refreshAdminSecuritySettings();
    await refreshAdminUsers();
  });
}
if (navSettingsButton) {
  navSettingsButton.addEventListener("click", async () => {
    setSettingsView();
    await refreshImportSettings();
  });
}
if (facebookCookieSaveButton) {
  facebookCookieSaveButton.addEventListener("click", async () => {
    const facebook_cookie = String(facebookCookieInput?.value || "").trim();
    if (!facebook_cookie) return;
    await apiFetch(`${API_BASE}/settings/import/facebook-cookie`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ facebook_cookie })
    });
    await refreshImportSettings();
  });
}
if (facebookCookieClearButton) {
  facebookCookieClearButton.addEventListener("click", async () => {
    await apiFetch(`${API_BASE}/settings/import/facebook-cookie`, { method: "DELETE" });
    await refreshImportSettings();
  });
}
if (facebookCookieTestButton) {
  facebookCookieTestButton.addEventListener("click", async () => {
    const response = await apiFetch(`${API_BASE}/settings/import/facebook-cookie/test`, { method: "POST" });
    if (!response.ok) return;
    const payload = await response.json();
    if (facebookCookieTestState) facebookCookieTestState.textContent = payload.message || payload.status || "";
  });
}

if (brandHomeButton) {
  brandHomeButton.addEventListener("click", navigateToDashboardHome);
}

sidebarToggleButtons.forEach((button) => {
  button.addEventListener("click", toggleSidePanel);
});

if (closeDetailButton) {
  closeDetailButton.addEventListener("click", hideRecipeDetail);
}

if (copyIngredientsButton) {
  copyIngredientsButton.addEventListener("click", copyIngredients);
}

if (detailAiCleanupButton) {
  detailAiCleanupButton.addEventListener("click", runDetailAiCleanup);
}

if (detailServingsDecreaseButton) {
  detailServingsDecreaseButton.addEventListener("click", () => {
    if (!formState.selectedRecipe) return;
    const nextServings = Math.max(1, detailIngredientDisplayState.targetServings - 1);
    detailIngredientDisplayState.targetServings = nextServings;
    if (detailServingsValueEl) detailServingsValueEl.textContent = formatKitchenQuantity(nextServings);
    detailServingsDecreaseButton.disabled = nextServings <= 1;
    renderDetailIngredients(formState.selectedRecipe);
  });
}

if (detailServingsIncreaseButton) {
  detailServingsIncreaseButton.addEventListener("click", () => {
    if (!formState.selectedRecipe) return;
    const nextServings = detailIngredientDisplayState.targetServings + 1;
    detailIngredientDisplayState.targetServings = nextServings;
    if (detailServingsValueEl) detailServingsValueEl.textContent = formatKitchenQuantity(nextServings);
    if (detailServingsDecreaseButton) detailServingsDecreaseButton.disabled = nextServings <= 1;
    renderDetailIngredients(formState.selectedRecipe);
  });
}

if (detailConvertButton) {
  detailConvertButton.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleDetailConvertMenu();
  });
}

if (detailConvertMenu) {
  detailConvertMenu.querySelectorAll("[data-convert-mode]").forEach((option) => {
    option.addEventListener("click", () => {
      setDetailConvertMode(option.dataset.convertMode || "original");
      closeDetailConvertMenu();
      if (formState.selectedRecipe) renderDetailIngredients(formState.selectedRecipe);
    });
  });
}

if (detailEditButton) {
  detailEditButton.addEventListener("click", () => {
    if (!formState.selectedRecipe) return;
    startEdit(formState.selectedRecipe);
  });
}

if (detailMenuButton) {
  detailMenuButton.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleDetailActionsMenu();
  });
}

if (detailMenuEditButton) {
  detailMenuEditButton.addEventListener("click", () => {
    closeDetailActionsMenu();
    if (!formState.selectedRecipe) return;
    startEdit(formState.selectedRecipe);
  });
}

if (detailMenuDeleteButton) {
  detailMenuDeleteButton.addEventListener("click", async () => {
    closeDetailActionsMenu();
    await deleteSelectedRecipe();
  });
}

if (detailGroceriesButton) {
  detailGroceriesButton.addEventListener("click", async () => {
    const recipeId = Number(formState.selectedRecipe?.id);
    if (!Number.isFinite(recipeId)) return;
    await openGroceryPreviewForRecipeIds([recipeId]);
  });
}

detailShareButton?.addEventListener("click", () => toggleShareModal(true));
closeShareModalButton?.addEventListener("click", () => toggleShareModal(false));
shareTextButton?.addEventListener("click", shareRecipeText);
copyTextButton?.addEventListener("click", copyRecipeText);
printRecipeButton?.addEventListener("click", printRecipe);

if (detailCookedToggle) {
  detailCookedToggle.addEventListener("change", async () => {
    const recipe = formState.selectedRecipe;
    if (!recipe?.id) return;
    const state = await saveRecipeUserState(recipe.id, { is_cooked: detailCookedToggle.checked });
    if (!state) return;
    updateRecipeInMemory(recipe.id, { is_cooked: state.is_cooked });
  });
}

if (detailRatingStars) {
  detailRatingStars.querySelectorAll("[data-rating-value]").forEach((starButton) => {
    starButton.addEventListener("click", async () => {
      const recipe = formState.selectedRecipe;
      if (!recipe?.id) return;
      const selectedRating = Number(starButton.dataset.ratingValue || "0");
      const state = await saveRecipeUserState(recipe.id, { rating: selectedRating });
      if (!state) return;
      updateRecipeInMemory(recipe.id, { rating: state.rating });
      updateRatingUi(selectedRating);
    });
  });
}

if (detailNoteInput) {
  detailNoteInput.addEventListener("input", () => {
    const recipe = formState.selectedRecipe;
    if (!recipe?.id) return;
    if (detailStateSaveTimer) window.clearTimeout(detailStateSaveTimer);
    detailStateSaveTimer = window.setTimeout(async () => {
      const state = await saveRecipeUserState(recipe.id, { personal_note: detailNoteInput.value });
      if (!state) return;
      updateRecipeInMemory(recipe.id, { personal_note: state.personal_note });
    }, 300);
  });
}

if (detailCookbookAddButton) {
  detailCookbookAddButton.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleDetailCookbookPopover();
  });
}

if (detailCookbookSaveButton) {
  detailCookbookSaveButton.addEventListener("click", saveDetailCookbookMembership);
}

if (detailCookbookOptions) {
  detailCookbookOptions.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement) || target.name !== "detail-cookbook-choice") return;

    const checkboxes = Array.from(
      detailCookbookOptions.querySelectorAll("input[name=\"detail-cookbook-choice\"]")
    );
    if (target.value === UNCATEGORIZED_COOKBOOK_ID && target.checked) {
      checkboxes.forEach((checkbox) => {
        if (checkbox !== target) checkbox.checked = false;
      });
    } else if (target.checked) {
      const uncategorized = checkboxes.find((checkbox) => checkbox.value === UNCATEGORIZED_COOKBOOK_ID);
      if (uncategorized) uncategorized.checked = false;
    }
    detailCookbookDraftSelection = getDetailCookbookSelectionFromUi();
  });
}

if (detailNewCookbookButton) {
  detailNewCookbookButton.addEventListener("click", async () => {
    const proposedName = window.prompt("Cookbook name?");
    const nextName = String(proposedName || "").trim();
    if (!nextName) return;
    if (!allCookbooks.some((name) => name.name.toLowerCase() === nextName.toLowerCase())) {
      await apiFetch(`${API_BASE}/cookbooks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nextName })
      });
      await loadRecipes();
    }
    detailCookbookDraftSelection = getDetailCookbookSelectionFromUi();
    const created = allCookbooks.find((cookbook) => cookbook.name.toLowerCase() === nextName.toLowerCase());
    if (created?.id) {
      detailCookbookDraftSelection.delete(UNCATEGORIZED_COOKBOOK_ID);
      detailCookbookDraftSelection.add(String(created.id));
    }
    if (detailCookbookOptions) renderDetailCookbookMembership(formState.selectedRecipe || {}, true);
  });
}

if (openAddRecipeButton) {
  openAddRecipeButton.addEventListener("click", () => {
    if (!isAuthenticated()) return;
    resetAddRecipeModalState();
    showAddRecipeModal();
  });
}

if (openAddRecipeRailButton) {
  openAddRecipeRailButton.addEventListener("click", () => {
    if (!isAuthenticated()) return;
    resetAddRecipeModalState();
    showAddRecipeModal();
  });
}

if (writeFromScratchOptionButton) {
  writeFromScratchOptionButton.addEventListener("click", startManualRecipe);
}

if (shoppingSelectionToggle) {
  shoppingSelectionToggle.addEventListener("click", () => {
    shoppingSelectionMode = !shoppingSelectionMode;
    if (!shoppingSelectionMode) selectedShoppingRecipeIds.clear();
    hideShoppingListView();
    applyRecipeFilters();
  });
}

if (generateShoppingListButton) {
  generateShoppingListButton.addEventListener("click", generateShoppingList);
}

selectAllRecipesButton?.addEventListener("click", () => {
  const visibleRecipes = getVisibleCookbookRecipes();
  if (!visibleRecipes.length) return;

  if (areAllVisibleRecipesSelected(visibleRecipes)) {
    selectedShoppingRecipeIds.clear();
  } else {
    selectedShoppingRecipeIds = new Set(
      visibleRecipes.map((recipe) => String(recipe?.id || "").trim()).filter(Boolean)
    );
  }

  applyRecipeFilters();
});

moveSelectedRecipesButton?.addEventListener("click", async () => {
  if (!selectedShoppingRecipeIds.size) return;
  try {
    await moveSelectedRecipesToCookbook();
  } catch (error) {
    if (shoppingListStatus) {
      shoppingListStatus.textContent = "Could not move selected recipes.";
      shoppingListStatus.classList.remove("hidden");
    }
  }
});

deleteSelectedRecipesButton?.addEventListener("click", async () => {
  const recipeIds = Array.from(selectedShoppingRecipeIds);
  if (!recipeIds.length) return;
  if (!window.confirm(`Delete ${recipeIds.length} selected recipe${recipeIds.length === 1 ? "" : "s"}?`)) return;
  for (const recipeId of recipeIds) {
    await apiFetch(`${API_BASE}/recipes/${recipeId}`, { method: "DELETE" });
  }
  resetShoppingSelection();
  await loadRecipes();
});

confirmGroceryPreviewButton?.addEventListener("click", async () => {
  const selectedIndexes = new Set(
    Array.from(groceryPreviewItems?.querySelectorAll("[data-grocery-preview-index]:checked") || [])
      .map((input) => Number(input.dataset.groceryPreviewIndex))
      .filter(Number.isInteger)
  );
  const selectedItems = pendingGroceryPreviewItems.filter((_, index) => selectedIndexes.has(index));
  if (!selectedItems.length) return;
  const groceryItems = selectedItems.map((item) => {
    const source = getPreviewItemSource(item);
    return {
      name: item.name || item.display_text || "",
      quantity: item.quantity ?? null,
      unit: item.unit ?? null,
      display_text: item.display_text || item.name || "",
      source_recipe_id: source?.recipe_id ?? null,
      source_recipe_title: source?.recipe_title ?? null,
    };
  });
  confirmGroceryPreviewButton.disabled = true;
  confirmGroceryPreviewButton.textContent = "Adding...";
  try {
    const response = await apiFetch(`${API_BASE}/grocery-list/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: groceryItems })
    });
    if (!response.ok) throw new Error("Add grocery items failed");
    renderShoppingList(await response.json());
    hideGroceryPreview();
    resetShoppingSelection();
    applyRecipeFilters();
    setGroceryListView();
  } finally {
    confirmGroceryPreviewButton.disabled = false;
    updateGroceryPreviewSelectionState();
  }
});

closeGroceryPreviewButton?.addEventListener("click", hideGroceryPreview);
groceryPreviewItems?.addEventListener("change", (event) => {
  const input = event.target.closest("[data-grocery-preview-index]");
  if (!input) return;
  updateGroceryPreviewSelectionState();
});

shoppingListItems?.addEventListener("change", async (event) => {
  const input = event.target.closest("[data-grocery-item-id]");
  if (!input) return;
  const response = await apiFetch(`${API_BASE}/grocery-list/items/${input.dataset.groceryItemId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ checked: input.checked })
  });
  if (response.ok) renderShoppingList(await response.json());
});

checkedGroceryItems?.addEventListener("change", async (event) => {
  const input = event.target.closest("[data-grocery-item-id]");
  if (!input) return;
  const response = await apiFetch(`${API_BASE}/grocery-list/items/${input.dataset.groceryItemId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ checked: input.checked })
  });
  if (response.ok) renderShoppingList(await response.json());
});

grocerySourceCards?.addEventListener("click", async (event) => {
  const openButton = event.target.closest("[data-grocery-source-open]");
  if (openButton) {
    const recipe = allRecipes.find((item) => String(item.id) === String(openButton.dataset.grocerySourceOpen));
    if (recipe) openRecipe(recipe);
    return;
  }
  const removeButton = event.target.closest("[data-grocery-source-remove]");
  if (!removeButton) return;
  const response = await apiFetch(`${API_BASE}/grocery-list/source/${removeButton.dataset.grocerySourceRemove}`, {
    method: "DELETE"
  });
  if (response.ok) renderShoppingList(await response.json());
});

clearCheckedGroceryButton?.addEventListener("click", async () => {
  const response = await apiFetch(`${API_BASE}/grocery-list/checked`, { method: "DELETE" });
  if (response.ok) renderShoppingList(await response.json());
});

clearGroceryListButton?.addEventListener("click", async () => {
  if (!window.confirm("Clear the grocery list?")) return;
  const response = await apiFetch(`${API_BASE}/grocery-list`, { method: "DELETE" });
  if (response.ok) renderShoppingList(await response.json());
});

if (closeShoppingListButton) {
  closeShoppingListButton.addEventListener("click", () => {
    navigateToDashboardHome();
  });
}

navMealPlanButton?.addEventListener("click", () => {
  setMealPlanView();
  loadMealPlanWeek();
});

navGroceriesButton?.addEventListener("click", async () => {
  await loadGroceryList({ show: true });
});

function closeOpenModalsForMobileNav() {
  hideAddRecipeModal();
  hideAiCleanupReview();
  mealPlanAddModal?.classList.add("hidden");
  mealPlanAddModal?.setAttribute("aria-hidden", "true");
  hideGroceryPreview();
}

mobileNavRecipesButton?.addEventListener("click", () => {
  if (!isAuthenticated()) return;
  closeOpenModalsForMobileNav();
  navigateToDashboardHome();
});

mobileNavMealPlanButton?.addEventListener("click", () => {
  if (!isAuthenticated()) return;
  closeOpenModalsForMobileNav();
  setMealPlanView();
  loadMealPlanWeek();
});

mobileNavGroceriesButton?.addEventListener("click", async () => {
  if (!isAuthenticated()) return;
  closeOpenModalsForMobileNav();
  await loadGroceryList({ show: true });
});

mobileAddButton?.addEventListener("click", () => {
  if (!isAuthenticated()) return;
  resetAddRecipeModalState();
  showAddRecipeModal();
});

if (cookbooksSectionToggle) {
  cookbooksSectionToggle.addEventListener("click", () => {
    setCookbooksSectionExpanded(!cookbooksSectionExpanded);
  });
}

if (closeAddRecipeButton) {
  closeAddRecipeButton.addEventListener("click", hideAddRecipeModal);
}

if (shareImportOpenButton) {
  shareImportOpenButton.addEventListener("click", () => {
    if (!shareImportOpenRecipeId) return;
    const matchingRecipe = allRecipes.find((recipe) => String(recipe.id) === String(shareImportOpenRecipeId));
    if (matchingRecipe) {
      openRecipe(matchingRecipe);
    }
  });
}

if (shareImportManualButton) {
  shareImportManualButton.addEventListener("click", () => {
    if (!shareImportManualPayload) return;
    prefillManualShareForm(shareImportManualPayload);
  });
}

if (loginForm) {
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = String(loginEmailInput?.value || "").trim();
    const password = String(loginPasswordInput?.value || "");

    if (loginError) {
      loginError.classList.add("hidden");
      loginError.textContent = "";
    }

    const response = await rawApiFetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });

    if (!response.ok) {
      if (loginError) {
        loginError.textContent = "Unable to sign in. Please try again later.";
        loginError.classList.remove("hidden");
      }
      return;
    }

    currentUser = await response.json();
    setAdminUsersAccessState();
    if (loginPasswordInput) loginPasswordInput.value = "";
    setAuthView(true);
    await initializeAuthenticatedApp();
    await autoImportPendingShare();
  });
}

if (adminAddUserForm) {
  adminAddUserForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = String(adminUserEmailInput?.value || "").trim();
    const displayName = String(adminUserDisplayNameInput?.value || "").trim();
    const password = String(adminUserPasswordInput?.value || "");
    const isAdmin = Boolean(adminUserIsAdminInput?.checked);
    const success = await runAdminAction(
      `${API_BASE}/admin/users`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          display_name: displayName || null,
          password,
          is_admin: isAdmin
        })
      },
      "User created."
    );
    if (!success) return;
    if (adminUserEmailInput) adminUserEmailInput.value = "";
    if (adminUserDisplayNameInput) adminUserDisplayNameInput.value = "";
    if (adminUserPasswordInput) adminUserPasswordInput.value = "";
    if (adminUserIsAdminInput) adminUserIsAdminInput.checked = false;
  });
}

if (adminSecuritySettingsForm) {
  adminSecuritySettingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      auth_lockout_enabled: Boolean(authLockoutEnabledInput?.checked),
      auth_max_failed_attempts: Math.max(1, Number(authMaxFailedAttemptsInput?.value || 1)),
      auth_lockout_minutes: Math.max(0, Number(authLockoutMinutesInput?.value || 0))
    };
    const success = await runAdminAction(
      `${API_BASE}/admin/security-settings`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      },
      "Security settings updated."
    );
    if (!success) return;
    await refreshAdminSecuritySettings();
  });
}

if (logoutButton) {
  logoutButton.addEventListener("click", async () => {
    await rawApiFetch(`${API_BASE}/auth/logout`, { method: "POST" });
    handleUnauthorized();
  });
}

if (addRecipeModal) {
  addRecipeModal.addEventListener("click", (event) => {
    if (event.target === addRecipeModal) hideAddRecipeModal();
  });
}

if (groceryPreviewModal) {
  groceryPreviewModal.addEventListener("click", (event) => {
    if (event.target === groceryPreviewModal) hideGroceryPreview();
  });
}

closeAiCleanupReviewButton?.addEventListener("click", cancelAiCleanupReview);
cancelAiCleanupReviewButton?.addEventListener("click", cancelAiCleanupReview);
acceptAiCleanupReviewButton?.addEventListener("click", acceptAiCleanupReview);

if (aiCleanupReviewModal) {
  aiCleanupReviewModal.addEventListener("click", (event) => {
    if (event.target === aiCleanupReviewModal) cancelAiCleanupReview();
  });
}

mealPlanPrevWeekButton?.addEventListener("click", async () => {
  mealPlanStartDate = new Date(mealPlanStartDate);
  mealPlanStartDate.setDate(mealPlanStartDate.getDate() - 7);
  await loadMealPlanWeek();
});
mealPlanNextWeekButton?.addEventListener("click", async () => {
  mealPlanStartDate = new Date(mealPlanStartDate);
  mealPlanStartDate.setDate(mealPlanStartDate.getDate() + 7);
  await loadMealPlanWeek();
});
mealPlanThisWeekButton?.addEventListener("click", async () => {
  mealPlanStartDate = getMondayDate(new Date());
  await loadMealPlanWeek();
});
function openMealPlanAddModal({ planDate, preferredRecipeId } = {}) {
  if (!mealPlanAddModal) return;
  pendingMealPlanDate = String(planDate || "").trim() || formatIsoDate(new Date());
  if (mealPlanDateInput) mealPlanDateInput.value = pendingMealPlanDate;
  if (mealPlanAddDateLabel) {
    const date = new Date(`${pendingMealPlanDate}T00:00:00`);
    mealPlanAddDateLabel.textContent = Number.isNaN(date.getTime())
      ? pendingMealPlanDate
      : date.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
  }
  if (mealPlanSlotSelect) mealPlanSlotSelect.value = "dinner";
  if (mealPlanRecipeSelect) {
    mealPlanRecipeSelect.innerHTML = allRecipes.map((r) => `<option value="${r.id}">${escapeHtml(r.title || "")}</option>`).join("");
    if (allRecipes.length > 0) {
      const preferredValue = String(preferredRecipeId || "");
      const preferredIndex = allRecipes.findIndex((recipe) => String(recipe.id) === preferredValue);
      mealPlanRecipeSelect.selectedIndex = preferredIndex >= 0 ? preferredIndex : 0;
    }
  }
  const hasRecipes = allRecipes.length > 0;
  if (mealPlanAddHelper) mealPlanAddHelper.classList.toggle("hidden", hasRecipes);
  if (confirmMealPlanAddButton) confirmMealPlanAddButton.disabled = !hasRecipes;
  mealPlanAddModal?.classList.remove("hidden");
  mealPlanAddModal?.setAttribute("aria-hidden", "false");
}

mealPlanDays?.addEventListener("click", async (event) => {
  const addButton = event.target.closest("[data-meal-plan-add]");
  if (addButton) {
    openMealPlanAddModal({ planDate: addButton.dataset.mealPlanAdd });
    return;
  }
  const removeButton = event.target.closest("[data-meal-plan-remove]");
  if (removeButton) {
    const response = await apiFetch(`${API_BASE}/meal-plan/items/${removeButton.dataset.mealPlanRemove}`, { method: "DELETE" });
    if (!response.ok) {
      if (mealPlanStatus) {
        mealPlanStatus.textContent = "Could not remove recipe. Try again.";
        mealPlanStatus.classList.remove("hidden");
      }
    } else if (mealPlanStatus) {
      mealPlanStatus.classList.add("hidden");
    }
    await loadMealPlanWeek();
    return;
  }
  const recipeOpenTarget = event.target.closest("[data-recipe-open]");
  if (recipeOpenTarget) {
    const recipe = allRecipes.find((item) => String(item.id) === String(recipeOpenTarget.dataset.recipeOpen || ""));
    if (recipe) openRecipe(recipe);
  }
});
confirmMealPlanAddButton?.addEventListener("click", async () => {
  const selectedPlanDate = String(mealPlanDateInput?.value || pendingMealPlanDate || "").trim();
  const response = await apiFetch(`${API_BASE}/meal-plan/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan_date: selectedPlanDate, recipe_id: Number(mealPlanRecipeSelect?.value || 0), meal_slot: String(mealPlanSlotSelect?.value || "dinner"), servings_override: "" })
  });
  mealPlanAddModal?.classList.add("hidden");
  mealPlanAddModal?.setAttribute("aria-hidden", "true");
  if (!response.ok) {
    if (mealPlanStatus) {
      mealPlanStatus.textContent = "Could not add recipe. Try again.";
      mealPlanStatus.classList.remove("hidden");
    }
  } else if (mealPlanStatus) {
    mealPlanStatus.classList.add("hidden");
  }
  await loadMealPlanWeek();
});
closeMealPlanAddModalButton?.addEventListener("click", () => {
  mealPlanAddModal?.classList.add("hidden");
  mealPlanAddModal?.setAttribute("aria-hidden", "true");
});
cancelMealPlanAddButton?.addEventListener("click", () => {
  mealPlanAddModal?.classList.add("hidden");
  mealPlanAddModal?.setAttribute("aria-hidden", "true");
});
shareModal?.addEventListener("click", (event) => {
  if (event.target === shareModal) toggleShareModal(false);
});

mealPlanAddModal?.addEventListener("click", (event) => {
  if (event.target === mealPlanAddModal) {
    mealPlanAddModal.classList.add("hidden");
    mealPlanAddModal.setAttribute("aria-hidden", "true");
  }
});
mealPlanGroceryButton?.addEventListener("click", async () => {
  const response = await apiFetch(`${API_BASE}/meal-plan/grocery-preview`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ start_date: formatIsoDate(mealPlanStartDate) })
  });
  if (!response.ok) return;
  const payload = await response.json();
  const items = Array.isArray(payload.items) ? payload.items : [];
  if (!items.length) {
    if (mealPlanStatus) {
      mealPlanStatus.textContent = "Add recipes to your week before generating a grocery list.";
      mealPlanStatus.classList.remove("hidden");
    }
    return;
  }
  if (mealPlanStatus) mealPlanStatus.classList.add("hidden");
  showGroceryPreview(applyGroceryPreviewDisplayMode(items));
});

// on load
window.addEventListener("load", async () => {
  // Capture shared payload as early as possible so auth redirects do not lose it.
  captureSharedPayloadFromQuery();

  setAuthView(false);
  setCookbooksSectionExpanded(loadCookbooksSectionPreference(), false);
  setSidePanelExpanded(loadSidePanelPreference(), false);
  setDashboardView();
  const isAuthed = await checkAuthSession();
  if (!isAuthed) return;
  await initializeAuthenticatedApp();
  await autoImportPendingShare();
});

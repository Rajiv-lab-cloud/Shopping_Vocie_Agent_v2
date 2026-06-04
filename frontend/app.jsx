const { useState, useEffect, useRef } = React;

const API_BASE = "";


// --- Helpers ---
function parseImage(urlStr) {
  if (!urlStr) return null;
  try {
    const arr = JSON.parse(urlStr);
    if (Array.isArray(arr) && arr.length > 0) return arr[0];
  } catch (e) {}
  
  if (typeof urlStr === 'string') {
    const parts = urlStr.split(',');
    if (parts.length > 0 && parts[0].trim().startsWith('http')) {
      return parts[0].trim();
    }
  }
  return null;
}

// --- Components ---

function Navbar({ cartCount, setView, onSearch }) {
  const [searchText, setSearchText] = useState("");

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && searchText.trim()) {
      onSearch(searchText.trim());
      setSearchText("");
    }
  };

  const handleSearchClick = () => {
    if (searchText.trim()) {
      onSearch(searchText.trim());
      setSearchText("");
    }
  };

  return (
    <nav className="navbar">
      <div className="nav-container">
        <div className="nav-logo" onClick={() => setView('home')}>
          AI-KART
          <i className="fas fa-robot"></i>
        </div>
        <div className="nav-search">
          <input 
            type="text" 
            placeholder="Ask for intelligent products..." 
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <i className="fas fa-search search-icon" onClick={handleSearchClick} style={{cursor: 'pointer'}}></i>
        </div>
        <div className="nav-actions">
          <button className="login-btn">Sign In</button>
          <button className="cart-btn" onClick={() => setView('cart')}>
            <i className="fas fa-shopping-bag"></i> Cart
            {cartCount > 0 && <span className="cart-badge">{cartCount}</span>}
          </button>
        </div>
      </div>
    </nav>
  );
}

function ProductGrid({ products, selectedCategory, onSelectProduct, addToCart, searchResultsIds }) {
  // Filter products by selected category
  const filteredProducts = products.filter(p => {
    if (selectedCategory === "Search Results" && searchResultsIds) {
      return searchResultsIds.includes(p.id);
    }
    if (selectedCategory === "All" || selectedCategory === "Search Results") return true;
    
    // Check if category name matches case-insensitively
    if (p.category_name && p.category_name.toLowerCase() === selectedCategory.toLowerCase()) {
      return true;
    }
    
    // Fallback to tags case-insensitively
    try {
      const tags = JSON.parse(p.tags || "[]");
      return tags.map(t => t.toLowerCase()).includes(selectedCategory.toLowerCase());
    } catch {
      return false;
    }
  });

  return (
    <div className="app-container">
      <h2 className="section-title">
        {selectedCategory === "All" ? "Curated Collection" : `${selectedCategory}`}
      </h2>
      <div className="product-grid">
        {filteredProducts.map(p => {
          const imgUrl = parseImage(p.image_url);
          return (
            <div key={p.id} className="product-card" onClick={() => onSelectProduct(p)}>
              <div className="product-image">
                {imgUrl ? (
                  <img src={imgUrl} alt={p.name} onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'block'; }} />
                ) : null}
                <i className="fas fa-box" style={{display: imgUrl ? 'none' : 'block'}}></i>
              </div>
              <div className="product-brand">{p.brand || 'AI-KART Studio'}</div>
              <div className="product-name">{p.name}</div>
              <div className="product-desc-short">{p.description}</div>
              <div className="product-rating">
                {(p.rating || 4.8).toFixed(1)} <i className="fas fa-star"></i>
              </div>
              <div className="price-row">
                <span className="price-current">₹{p.price.toFixed(2)}</span>
                {p.original_price > p.price && (
                  <span className="price-original">₹{p.original_price.toFixed(2)}</span>
                )}
              </div>
              <button 
                className="btn-primary" 
                onClick={(e) => {
                  e.stopPropagation();
                  addToCart(p);
                }}
              >
                Add to Cart
              </button>
            </div>
          );
        })}
        {filteredProducts.length === 0 && <p style={{color: 'var(--text-muted)'}}>No products found for this category.</p>}
      </div>
    </div>
  );
}

function ProductDetail({ product, allProducts, onBack, addToCart, onSelectProduct }) {
  if (!product) return null;
  const imgUrl = parseImage(product.image_url);

  // Find related products
  const related = allProducts
    .filter(p => p.id !== product.id && p.category_name === product.category_name)
    .slice(0, 4);

  return (
    <div className="app-container">
      <div className="back-btn" onClick={onBack}>
        <i className="fas fa-arrow-left"></i> Back to collection
      </div>
      
      <div className="detail-container">
        <div className="detail-image-box">
          {imgUrl ? (
            <img src={imgUrl} alt={product.name} onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'block'; }} />
          ) : null}
          <i className="fas fa-box" style={{display: imgUrl ? 'none' : 'block', fontSize: '5rem', color: 'var(--border-color)'}}></i>
        </div>
        <div className="detail-info">
          <div className="detail-brand">{product.brand || 'AI-KART Studio'}</div>
          <h1 className="detail-title">{product.name}</h1>
          
          <div className="product-rating" style={{marginBottom: '1.5rem', alignSelf: 'flex-start'}}>
            <span>{(product.rating || 4.8).toFixed(1)}</span>
            <i className="fas fa-star" style={{marginLeft: '4px'}}></i>
            <span style={{color: 'var(--text-muted)', marginLeft: '8px', fontWeight: 500}}>({product.review_count || 120} reviews)</span>
          </div>

          <div className="detail-price-row">
            <div className="detail-price">₹{product.price.toFixed(2)}</div>
            {product.original_price > product.price && (
              <div className="price-original" style={{fontSize: '1.25rem'}}>₹{product.original_price.toFixed(2)}</div>
            )}
          </div>

          <p className="detail-desc">
            {product.description}
          </p>
          
          <button className="btn-primary" onClick={() => addToCart(product)}>
            <i className="fas fa-shopping-bag"></i> Add to Cart
          </button>
        </div>
      </div>

      {related.length > 0 && (
        <div style={{marginTop: '4rem'}}>
          <h3 style={{marginBottom: '1.5rem', color: 'var(--text-primary)', fontSize: '1.5rem', fontWeight: 700}}>Complete the look</h3>
          <div className="product-grid" style={{gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))'}}>
            {related.map(p => {
              const relImg = parseImage(p.image_url);
              return (
                <div key={p.id} className="product-card" onClick={() => onSelectProduct(p)}>
                  <div className="product-image" style={{height: '160px'}}>
                    {relImg ? (
                      <img src={relImg} alt={p.name} onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'block'; }} />
                    ) : null}
                    <i className="fas fa-box" style={{display: relImg ? 'none' : 'block'}}></i>
                  </div>
                  <div className="product-name" style={{fontSize: '0.9rem'}}>{p.name}</div>
                  <div className="price-current" style={{fontSize: '1.1rem'}}>₹{p.price.toFixed(2)}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function CartView({ cartItems, removeFromCart, onCheckout }) {
  const total = cartItems.reduce((sum, item) => sum + (item.price * item.quantity), 0);

  return (
    <div className="app-container">
      <div style={{display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '2rem'}}>
        <div className="cart-container-box">
          <h3 style={{marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem', fontSize: '1.5rem', fontWeight: 700}}>My Cart ({cartItems.length})</h3>
          {cartItems.map(item => (
            <div key={item.cart_id} className="cart-item">
              <div className="cart-item-image">
                {parseImage(item.image_url) ? (
                  <img src={parseImage(item.image_url)} alt={item.name} onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'block'; }} />
                ) : null}
                <i className="fas fa-box" style={{display: parseImage(item.image_url) ? 'none' : 'block', fontSize: '2rem', color: 'var(--border-color)'}}></i>
              </div>
              <div style={{flex: '1', display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
                <h4 style={{fontSize: '1.15rem', marginBottom: '0.25rem', color: 'var(--text-primary)', fontWeight: 700}}>{item.name}</h4>
                <div style={{color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '1rem', fontWeight: 500}}>Qty: {item.quantity}</div>
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                  <div style={{fontSize: '1.4rem', fontWeight: 800, color: 'var(--text-primary)'}}>₹{(item.price * item.quantity).toFixed(2)}</div>
                  <button onClick={() => removeFromCart(item.cart_id)} style={{background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontWeight: '700', fontSize: '0.85rem', letterSpacing: '1px'}}>REMOVE</button>
                </div>
              </div>
            </div>
          ))}
          {cartItems.length === 0 && <p style={{padding: '3rem 0', color: 'var(--text-muted)', textAlign: 'center', fontSize: '1.1rem'}}>Your cart feels light. Let's add something intelligent!</p>}
        </div>
        
        <div className="cart-summary">
          <h3 style={{marginBottom: '1.5rem', paddingBottom: '1rem', fontSize: '1.1rem', fontWeight: 700, letterSpacing: '1px'}}>ORDER SUMMARY</h3>
          <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '1rem', color: 'rgba(255,255,255,0.8)'}}>
            <span>Price ({cartItems.length} items)</span>
            <span style={{fontWeight: 600}}>₹{total.toFixed(2)}</span>
          </div>
          <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem', color: 'rgba(255,255,255,0.8)'}}>
            <span>Delivery Charges</span>
            <span style={{color: 'var(--success)', fontWeight: 700}}>FREE</span>
          </div>
          <div style={{display: 'flex', justifyContent: 'space-between', borderTop: '1px dashed rgba(255,255,255,0.2)', paddingTop: '1.5rem', marginBottom: '2rem', fontSize: '1.4rem', fontWeight: '800'}}>
            <span>Total Amount</span>
            <span>₹{total.toFixed(2)}</span>
          </div>
          <button className="btn-primary" onClick={onCheckout}>CHECKOUT NOW</button>
        </div>
      </div>
    </div>
  );
}

function ToastContainer({ toasts }) {
  return (
    <div className="toast-container">
      {toasts.map(toast => (
        <div key={toast.id} className="toast">
          <i className="fas fa-check-circle toast-icon"></i>
          <span className="toast-content">{toast.message}</span>
        </div>
      ))}
    </div>
  );
}

function VoiceOrb({ onNavigate, onAddToCart, onRemoveFromCart, onUpdateCartQuantity, onClearCart, onFilterCategory, onSelectProductById, onShowProducts, products }) {
  const [state, setState] = useState('idle'); // idle, listening, processing
  const [message, setMessage] = useState('');
  const [conversationHistory, setConversationHistory] = useState([]);
  
  const mediaRecorder = useRef(null);
  const audioChunks = useRef([]);
  const audioObj = useRef(null);

  const startRecording = async () => {
    if (state === 'processing') return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder.current = new MediaRecorder(stream);
      audioChunks.current = [];

      mediaRecorder.current.ondataavailable = e => {
        if (e.data.size > 0) audioChunks.current.push(e.data);
      };

      mediaRecorder.current.onstop = () => {
        processAudioStream();
        stream.getTracks().forEach(t => t.stop());
      };

      mediaRecorder.current.start();
      setState('listening');
      setMessage('Listening...');
      if (audioObj.current) audioObj.current.pause();
    } catch (err) {
      console.error(err);
      setMessage("Mic access denied");
    }
  };

  const stopRecording = () => {
    window.speechSynthesis.cancel();
    if (mediaRecorder.current && mediaRecorder.current.state === "recording") {
      mediaRecorder.current.stop();
    }
  };

  const processAudioStream = async () => {
    setState('processing');
    setMessage('AI thinking...');
    
    const audioBlob = new Blob(audioChunks.current, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append("audio", audioBlob, "voice.webm");
    formData.append("conversation_history", JSON.stringify(conversationHistory));

    try {
      const res = await fetch(`${API_BASE}/v1/shop/stream`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error("Stream failed");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        // SSE lines end with \n\n
        let boundary = buffer.indexOf("\n\n");
        while (boundary !== -1) {
          const chunk = buffer.substring(0, boundary);
          buffer = buffer.substring(boundary + 2);
          
          if (chunk.startsWith("data: ")) {
            try {
              const data = JSON.parse(chunk.substring(6));
              
              if (data.event === "transcript") {
                const t = data.data.transcript;
                setMessage(`You: ${t}`);
                setConversationHistory(prev => [
                  ...prev.slice(-10),
                  { role: 'user', content: t }
                ]);
              } 
              else if (data.event === "actions") {
                // Execute UI actions instantly while TTS is still generating!
                const actions = data.data.ui_actions || [];
                actions.forEach(act => {
                  const params = act.params || {};
                  if (act.action === "NAVIGATE_TO") {
                    onNavigate(params.page || 'home');
                  } else if (act.action === "ADD_TO_CART" && params.product_id) {
                    const product = products.find(p => p.id === params.product_id);
                    if (product) onAddToCart(product, params.quantity || 1);
                  } else if (act.action === "UPDATE_CART_QUANTITY" && params.product_id && params.quantity !== undefined) {
                    if (onUpdateCartQuantity) onUpdateCartQuantity(params.product_id, params.quantity);
                  } else if (act.action === "REMOVE_FROM_CART" && params.product_id) {
                    if (onRemoveFromCart) onRemoveFromCart(params.product_id);
                  } else if (act.action === "CLEAR_CART") {
                    if (onClearCart) onClearCart();
                  } else if (act.action === "FILTER_PRODUCTS" && params.category) {
                    onFilterCategory(params.category);
                  } else if (act.action === "SHOW_PRODUCT_DETAIL" && params.product_id) {
                    onSelectProductById(params.product_id);
                  } else if (act.action === "SHOW_PRODUCTS") {
                    if (params.product_ids) {
                      onShowProducts(params.product_ids);
                    } else {
                      onNavigate('home');
                    }
                  } else if (act.action === "CHECKOUT") {
                    fetch(`${API_BASE}/v1/cart/checkout`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ 
                        address: params.address, 
                        payment_method: params.payment_method 
                      })
                    })
                    .then(res => {
                      if (!res.ok) throw new Error("Checkout failed");
                      return res.blob();
                    })
                    .then(blob => {
                      const url = window.URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.style.display = 'none';
                      a.href = url;
                      a.download = 'ShopBot_Invoice.pdf';
                      document.body.appendChild(a);
                      a.click();
                      window.URL.revokeObjectURL(url);
                      
                      // Refresh cart UI
                      if (onClearCart) {
                        onClearCart();
                      }
                    })
                    .catch(err => console.error("Checkout error:", err));
                  }
                });
              } 
              else if (data.event === "audio") {
                // Audio is ready, play it and update UI message
                const responseText = data.data.response_text || "Done.";
                setMessage(responseText.length > 80 ? responseText.substring(0, 80) + '...' : responseText);
                
                setConversationHistory(prev => [
                  ...prev.slice(-10),
                  { role: 'assistant', content: responseText }
                ]);
                
                const audioB64 = data.data.audio_b64;
                if (audioB64) {
                  if (audioObj.current) audioObj.current.pause();
                  audioObj.current = new Audio("data:audio/mp3;base64," + audioB64);
                  audioObj.current.play();
                } else {
                  // Fallback to browser TTS
                  const utterance = new SpeechSynthesisUtterance(responseText);
                  const voices = window.speechSynthesis.getVoices();
                  const femaleVoice = voices.find(v =>
                    /female|zira|samantha|victoria|karen|hazel/i.test(v.name)
                  );
                  if (femaleVoice) utterance.voice = femaleVoice;
                  window.speechSynthesis.speak(utterance);
                }
                
                setTimeout(() => setState('idle'), 3000);
              } 
              else if (data.event === "error") {
                setMessage(data.data.error || "Error processing voice.");
                setState('idle');
              }
            } catch(e) {
              console.error("SSE JSON parse error", e);
            }
          }
          boundary = buffer.indexOf("\n\n");
        }
      }
    } catch (err) {
      console.error(err);
      setMessage("Connection error.");
      setState('idle');
    }
  };

  return (
    <div className="voice-orb-container">
      <div className={`voice-tooltip ${state !== 'idle' || message ? 'visible' : ''}`}>
        {message || "Hold to speak with AI-KART"}
      </div>
      <button 
        className={`voice-orb ${state === 'listening' ? 'listening' : state === 'processing' ? 'processing' : ''}`}
        onMouseDown={startRecording}
        onMouseUp={stopRecording}
        onMouseLeave={stopRecording}
      >
        <i className="fas fa-microphone orb-icon"></i>
      </button>
    </div>
  );
}

// --- Main App ---

const CATEGORIES = ["All", "Beauty", "Fragrances", "Furniture", "Groceries"];

function mapCategoryName(target) {
  const clean = (target || '').toLowerCase().replace('category/', '').trim();
  if (clean === 'beauty' || clean === 'makeup' || clean === 'skincare' || clean === 'skin-care' || clean === 'skin care') {
    return 'Beauty';
  }
  if (clean === 'fragrances' || clean === 'fragrance' || clean === 'perfume' || clean === 'perfumes' || clean === 'scents') {
    return 'Fragrances';
  }
  if (clean === 'furniture' || clean === 'decor' || clean === 'home-decoration' || clean === 'home decor' || clean === 'bed' || clean === 'sofa') {
    return 'Furniture';
  }
  if (clean === 'groceries' || clean === 'food' || clean === 'grocery' || clean === 'fruit' || clean === 'vegetables') {
    return 'Groceries';
  }
  
  const match = CATEGORIES.find(c => c.toLowerCase().includes(clean) || clean.includes(c.toLowerCase()));
  return match || null;
}


function App() {
  const [view, setView] = useState('home'); 
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [products, setProducts] = useState([]);
  const [cartItems, setCartItems] = useState([]);

  const handleTextSearch = async (text) => {
    if (!text.trim()) return;
    
    showToast(`Searching for: "${text}"...`);
    
    const formData = new FormData();
    formData.append("text", text);
    formData.append("skip_tts", "true");
    
    try {
      const res = await fetch(`${API_BASE}/v1/shop`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error("Search failed");
      const data = await res.json();
      
      if (data.response_text) {
        showToast(data.response_text);
      }
      
      const actions = data.ui_actions || [];
      actions.forEach(act => {
        const params = act.params || {};
        if (act.action === "NAVIGATE_TO") {
          handleNavigate(params.page || 'home');
        } else if (act.action === "ADD_TO_CART" && params.product_id) {
          const product = products.find(p => p.id === params.product_id);
          if (product) addToCart(product, params.quantity || 1);
        } else if (act.action === "UPDATE_CART_QUANTITY" && params.product_id && params.quantity !== undefined) {
          updateCartQuantity(params.product_id, params.quantity);
        } else if (act.action === "REMOVE_FROM_CART" && params.product_id) {
          removeFromCartByProductId(params.product_id);
        } else if (act.action === "CLEAR_CART") {
          clearCart();
        } else if (act.action === "FILTER_PRODUCTS" && params.category) {
          handleFilterCategory(params.category);
        } else if (act.action === "SHOW_PRODUCT_DETAIL" && params.product_id) {
          handleSelectProductById(params.product_id);
        } else if (act.action === "SHOW_PRODUCTS") {
          if (params.product_ids) {
            handleShowProducts(params.product_ids);
          } else {
            handleNavigate('home');
          }
        }
      });
    } catch (err) {
      console.error(err);
      showToast("Search failed or service unavailable.");
    }
  };
  const [toasts, setToasts] = useState([]);
  const [searchResultsIds, setSearchResultsIds] = useState(null);

  useEffect(() => {
    if (selectedCategory === "Search Results") return; // Handled manually by handleShowProducts
    let url = `${API_BASE}/v1/products`;
    if (selectedCategory && selectedCategory !== "All") {
      url += `?category=${encodeURIComponent(selectedCategory)}`;
    }
    fetch(url)
      .then(res => res.json())
      .then(data => setProducts(data))
      .catch(err => console.error(err));
  }, [selectedCategory]);

  useEffect(() => {
    loadCart();
  }, []);

  const loadCart = () => {
    fetch(`${API_BASE}/v1/cart`)
      .then(res => res.json())
      .then(data => setCartItems(data))
      .catch(err => console.error(err));
  };

  const showToast = (message) => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3000);
  };

  const addToCart = (product, quantity = 1) => {
    fetch(`${API_BASE}/v1/cart/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: product.id, quantity })
    }).then(() => {
      loadCart();
      showToast(`Added ${product.name.substring(0, 20)}... to cart!`);
    });
  };

  const updateCartQuantity = (productId, quantity) => {
    fetch(`${API_BASE}/v1/cart/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, quantity })
    }).then(() => loadCart());
  };

  const removeFromCart = (cartId) => {
    fetch(`${API_BASE}/v1/cart/${cartId}`, { method: 'DELETE' })
      .then(() => loadCart());
  };

  const removeFromCartByProductId = (productId) => {
    const item = cartItems.find(i => i.id === productId);
    if (item) removeFromCart(item.cart_id);
  };

  const clearCart = () => {
    fetch(`${API_BASE}/v1/cart`, { method: 'DELETE' })
      .then(() => {
        loadCart();
        showToast('Cart cleared!');
      });
  };

  const handleCheckout = () => {
    fetch(`${API_BASE}/v1/cart/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        address: "Not Provided", 
        payment_method: "Not Provided" 
      })
    })
    .then(res => {
      if (!res.ok) throw new Error("Checkout failed");
      return res.blob();
    })
    .then(blob => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = 'ShopBot_Invoice.pdf';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      
      clearCart();
    })
    .catch(err => {
      console.error("Checkout error:", err);
      showToast("Checkout failed. Cart might be empty!");
    });
  };

  const handleNavigate = (target) => {
    let cleanTarget = (target || '').toLowerCase().replace('category/', '').trim();
    if (cleanTarget === 'home' || cleanTarget === 'cart') {
      setView(cleanTarget);
      if (cleanTarget === 'home') setSelectedProduct(null);
      return;
    }
    
    const mapped = mapCategoryName(target);
    if (mapped) {
      setSelectedCategory(mapped);
      setView('home');
      setSelectedProduct(null);
    } else {
      setView('home');
      setSelectedProduct(null);
    }
  };

  const handleFilterCategory = (category) => {
    setSearchResultsIds(null); // Clear search results when filtering
    const mapped = mapCategoryName(category);
    if (mapped) {
      setSelectedCategory(mapped);
    } else {
      setSelectedCategory('All');
    }
    setView('home');
    setSelectedProduct(null);
  };

  const handleShowProducts = (productIds) => {
    setSearchResultsIds(productIds);
    setSelectedCategory('Search Results');
    setView('home');
    setSelectedProduct(null);

    // Fetch the specific products from the backend since they might not be in the initial 50
    fetch(`${API_BASE}/v1/products/by-ids?ids=${productIds.join(',')}`)
      .then(res => res.json())
      .then(data => {
        setProducts(prev => {
          const newProducts = [...prev];
          data.forEach(d => {
            if (!newProducts.find(p => p.id === d.id)) {
              newProducts.push(d);
            }
          });
          return newProducts;
        });
      })
      .catch(err => console.error(err));
  };

  const handleSelectProductById = (productId) => {
    const product = products.find(p => p.id === productId);
    if (product) {
      setSelectedProduct(product);
      setView('detail');
    }
  };

  const handleProductSelect = (product) => {
    setSelectedProduct(product);
    setView('detail');
  };

  return (
    <div>
      <Navbar cartCount={cartItems.length} setView={handleNavigate} onSearch={handleTextSearch} />
      
      {view === 'home' && (
        <div className="app-container" style={{paddingBottom: '0', marginBottom: '0'}}>
          <div className="category-nav">
            {CATEGORIES.map(cat => (
              <div 
                key={cat} 
                className={`category-tab ${selectedCategory === cat ? 'active' : ''}`}
                onClick={() => setSelectedCategory(cat)}
              >
                {cat}
              </div>
            ))}
          </div>
        </div>
      )}

      {view === 'home' && (
        <ProductGrid 
          products={products}
          searchResultsIds={searchResultsIds}
          addToCart={addToCart} 
          selectedCategory={selectedCategory}
          onSelectProduct={handleProductSelect}
        />
      )}
      
      {view === 'detail' && selectedProduct && (
        <ProductDetail 
          product={selectedProduct} 
          allProducts={products}
          onBack={() => setView('home')}
          addToCart={addToCart}
          onSelectProduct={handleProductSelect}
        />
      )}

      {view === 'cart' && (
        <CartView 
          cartItems={cartItems} 
          removeFromCart={removeFromCart} 
          onCheckout={handleCheckout}
        />
      )}
      
      <VoiceOrb 
        onNavigate={handleNavigate} 
        onAddToCart={addToCart}
        onUpdateCartQuantity={updateCartQuantity}
        onRemoveFromCart={removeFromCartByProductId}
        onClearCart={clearCart}
        onFilterCategory={handleFilterCategory}
        onSelectProductById={handleSelectProductById}
        onShowProducts={handleShowProducts}
        products={products}
      />
      
      <ToastContainer toasts={toasts} />
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);

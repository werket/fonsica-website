# Fonsica.se Website

Your new personal consulting website for iGaming & Lottery consultancy.

---

## Quick Preview

To preview the website locally before publishing:

1. Open the `index.html` file directly in your browser (just double-click it)
2. Or use VS Code with the "Live Server" extension

---

## Step-by-Step: Host on GitHub Pages

### Step 1: Create a GitHub Repository

1. Go to [github.com](https://github.com) and log in
2. Click the **+** icon (top right) → **New repository**
3. Name it: `fonsica.se` (or any name you prefer)
4. Set it to **Public** (required for free GitHub Pages)
5. Click **Create repository**

### Step 2: Upload Your Website Files

**Option A: Using GitHub.com (easiest)**

1. On your new repository page, click **"uploading an existing file"**
2. Drag and drop the `index.html` file
3. Click **Commit changes**

**Option B: Using Git command line**

```bash
# Navigate to your website folder
cd path/to/fonsica-website

# Initialize git
git init

# Add all files
git add .

# Create first commit
git commit -m "Initial website"

# Add your GitHub repo as remote (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/fonsica.se.git

# Push to GitHub
git push -u origin main
```

### Step 3: Enable GitHub Pages

1. Go to your repository on GitHub
2. Click **Settings** (tab at the top)
3. Scroll down to **Pages** in the left sidebar
4. Under "Source", select **Deploy from a branch**
5. Select **main** branch and **/ (root)** folder
6. Click **Save**
7. Wait 1-2 minutes, then refresh — you'll see your site URL: `https://YOUR_USERNAME.github.io/fonsica.se`

---

## Step-by-Step: Connect Your Domain (fonsica.se)

### Step 4: Configure GitHub for Custom Domain

1. In your repository, go to **Settings** → **Pages**
2. Under "Custom domain", enter: `fonsica.se`
3. Click **Save**
4. Check **Enforce HTTPS** (after DNS propagates)

GitHub will create a file called `CNAME` in your repository.

### Step 5: Configure DNS at Loopia

1. Log in to [loopia.se](https://loopia.se)
2. Go to your domain management for **fonsica.se**
3. Find **DNS Settings** or **Zone file**

**Add these DNS records:**

| Type  | Host/Name | Value/Points to              | TTL    |
|-------|-----------|------------------------------|--------|
| A     | @         | 185.199.108.153             | 3600   |
| A     | @         | 185.199.109.153             | 3600   |
| A     | @         | 185.199.110.153             | 3600   |
| A     | @         | 185.199.111.153             | 3600   |
| CNAME | www       | YOUR_USERNAME.github.io.     | 3600   |

**Note:** Replace `YOUR_USERNAME` with your actual GitHub username. The trailing dot after `.io` is important for some DNS providers.

### Step 6: Wait for DNS Propagation

- DNS changes can take 15 minutes to 48 hours
- You can check propagation at [dnschecker.org](https://dnschecker.org)
- Once propagated, your site will be live at `https://fonsica.se`

---

## Updating Your Website

To make changes after initial setup:

**Using GitHub.com:**
1. Go to your repository
2. Click on `index.html`
3. Click the pencil icon to edit
4. Make changes and click **Commit changes**
5. Changes go live in 1-2 minutes

**Using Git:**
```bash
# After editing files locally
git add .
git commit -m "Description of changes"
git push
```

---

## Adding Your Photo

Replace the placeholder avatar:

1. Add your photo to the repository (e.g., `photo.jpg`)
2. In `index.html`, find the emoji placeholders (👤)
3. Replace with: `<img src="photo.jpg" alt="Adam Fonsica">`
4. Add appropriate CSS styling for the image

---

## Customization Tips

### Update Calendly Link
Find this line and replace with your actual Calendly URL:
```html
<a href="https://calendly.com" ...>
```

### Add More Speaking Events
Copy an existing `speaking-item` div and modify the content.

### Change Colors
Edit the CSS variables at the top of the file:
```css
:root {
    --primary: #6366f1;      /* Main accent color */
    --accent: #f472b6;       /* Secondary accent */
    --dark: #0f0f1a;         /* Background */
}
```

---

## Need Help?

If you run into issues:
- GitHub Pages docs: https://docs.github.com/en/pages
- Loopia support: https://support.loopia.se

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import re
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="Dashboard Call Center 112",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main {
        padding: 0rem 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

# ========== PATH FILE ==========
PATH_2024 = "LAPORAN INSIDEN CALL CENTER 112 TAHUN 2024.xlsx"
PATH_2025 = "LAPORAN INSIDEN CALLCENTER 112 TAHUN 2025.xlsx"
# ===============================

# Helper function untuk parsing durasi
def parse_duration_to_seconds(duration_str):
    """
    Parse durasi format: '0 Hari : 20 Jam : 41 Menit : 56 Detik'
    Return total seconds
    """
    if pd.isna(duration_str):
        return np.nan
    
    duration_str = str(duration_str).strip()
    
    # Pattern untuk format: "X Hari : Y Jam : Z Menit : W Detik"
    pattern = r'(\d+)\s*Hari\s*:\s*(\d+)\s*Jam\s*:\s*(\d+)\s*Menit\s*:\s*(\d+)\s*Detik'
    match = re.search(pattern, duration_str)
    
    if match:
        days = int(match.group(1))
        hours = int(match.group(2))
        minutes = int(match.group(3))
        seconds = int(match.group(4))
        
        total_seconds = days * 86400 + hours * 3600 + minutes * 60 + seconds
        return total_seconds
    
    return np.nan

# Cache data loading
@st.cache_data
def load_and_process_data(path_2024, path_2025):
    """Load dan preprocess data dari 2 file Excel"""
    
    try:
        # Load data
        df24 = pd.read_excel(path_2024)
        df25 = pd.read_excel(path_2025)
        
        # Tambah kolom source
        df24['source'] = '2024'
        df25['source'] = '2025'
        
        # Gabung dataset
        df = pd.concat([df24, df25], ignore_index=True)
        
        # Bersihkan nama kolom
        df.columns = [c.strip() for c in df.columns]
        
        # Konversi waktu lapor ke datetime
        df['WAKTU LAPOR'] = pd.to_datetime(df['WAKTU LAPOR'], errors='coerce')
        
        # Buat fitur turunan dari waktu
        df['date'] = df['WAKTU LAPOR'].dt.date
        df['year'] = df['WAKTU LAPOR'].dt.year
        df['month'] = df['WAKTU LAPOR'].dt.month
        df['ym'] = df['WAKTU LAPOR'].dt.to_period('M')
        df['day'] = df['WAKTU LAPOR'].dt.day
        df['hour'] = df['WAKTU LAPOR'].dt.hour
        df['weekday'] = df['WAKTU LAPOR'].dt.day_name()
        
        # Parse durasi pengerjaan
        if 'DURASI PENGERJAAN' in df.columns:
            df['duration_seconds'] = df['DURASI PENGERJAAN'].apply(parse_duration_to_seconds)
        else:
            df['duration_seconds'] = np.nan
        
        # Bersihkan tipe laporan (PENTING: data menggunakan lowercase!)
        if 'TIPE LAPORAN' in df.columns:
            df['TIPE LAPORAN'] = df['TIPE LAPORAN'].astype(str).str.strip().str.lower()
        else:
            df['TIPE LAPORAN'] = 'unknown'
        
        # Cleaning kecamatan & kelurahan
        for c in ['KECAMATAN', 'KELURAHAN']:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip()
                df[c] = df[c].replace({'-': pd.NA, 'nan': pd.NA, '': pd.NA})
                df[c] = df[c].where(df[c].isna(), df[c].str.title())
        
        # === DETEKSI GHOST CALL ===
        # Ghost call terdeteksi dari TIPE LAPORAN = 'ghost'
        df['ghost_call'] = df['TIPE LAPORAN'] == 'ghost'
        
        # === DETEKSI PRANK CALL ===
        # Prank call terdeteksi dari TIPE LAPORAN = 'prank'
        df['prank_call'] = df['TIPE LAPORAN'] == 'prank'
        
        # === DETEKSI SHORT CALL ===
        # Short call: durasi <= 5 detik
        df['short_call'] = (df['duration_seconds'] <= 5) & (df['duration_seconds'].notna())
        
        # === DETEKSI LOKASI PALSU ===
        # Lokasi palsu: LATITUDE = 0 dan LONGITUDE = 0
        df['fake_location'] = False
        if 'LATITUDE' in df.columns and 'LONGITUDE' in df.columns:
            df['LATITUDE'] = pd.to_numeric(df['LATITUDE'], errors='coerce')
            df['LONGITUDE'] = pd.to_numeric(df['LONGITUDE'], errors='coerce')
            df['fake_location'] = (df['LATITUDE'] == 0) & (df['LONGITUDE'] == 0)
        
        # === DETEKSI SPAM BERULANG ===
        # Spam: panggilan dari UID yang sama dalam waktu < 2 menit
        df_sorted = df.sort_values('WAKTU LAPOR').copy()
        if 'UID' in df.columns:
            df_sorted['prev_time'] = df_sorted.groupby('UID')['WAKTU LAPOR'].shift(1)
            df_sorted['diff_min'] = (df_sorted['WAKTU LAPOR'] - df_sorted['prev_time']).dt.total_seconds() / 60
            df_sorted['rapid_repeat'] = (df_sorted['diff_min'] <= 2) & (df_sorted['diff_min'].notna())
            df = df_sorted
        else:
            df['rapid_repeat'] = False
        
        return df, None
    
    except FileNotFoundError as e:
        return None, f"❌ File tidak ditemukan: {e}"
    except Exception as e:
        return None, f"❌ Error saat memuat data: {str(e)}"

# Main app
def main():
    st.title("📞 Dashboard Analisis Call Center 112")
    st.markdown("**Dashboard Interaktif untuk Mengeksplorasi Pola, Tren, dan Insight Data Laporan Call Center**")
    st.markdown("---")
    
    # Load data otomatis
    with st.spinner('⏳ Memuat dan memproses data...'):
        df, error = load_and_process_data(PATH_2024, PATH_2025)
    
    if error:
        st.error(error)
        st.info("💡 **Tips:** Pastikan file Excel ada di folder yang sama dengan dashboard.py")
        return
    
    st.success(f"✅ Data berhasil dimuat! Total: {len(df):,} laporan")
    
    # Sidebar - Filters
    st.sidebar.header("🔍 Filter Data")
    
    # Filter tahun
    years = sorted(df['source'].unique())
    selected_years = st.sidebar.multiselect("Pilih Tahun", years, default=years)
    
    # Filter kategori (exclude "-" yang biasanya untuk ghost/prank)
    if 'KATEGORI' in df.columns:
        # Ambil kategori unik dan filter yang bukan "-" atau kosong
        all_categories = df['KATEGORI'].fillna('-').unique()
        valid_categories = sorted([c for c in all_categories if c not in ['-', '', 'nan']])
        
        # Tambahkan opsi untuk data tanpa kategori (ghost/prank)
        category_options = ['[Tanpa Kategori (Ghost/Prank)]'] + valid_categories
        
        # Jika ada kategori valid, tampilkan filter
        if len(valid_categories) > 0:
            selected_categories = st.sidebar.multiselect(
                "Pilih Kategori (opsional)", 
                category_options,
                default=[],  # Default kosong = tampilkan semua
                help="Pilih '[Tanpa Kategori]' untuk ghost/prank, kosongkan untuk semua data"
            )
        else:
            selected_categories = []
    else:
        selected_categories = []
    
    # Filter kecamatan
    if 'KECAMATAN' in df.columns:
        # Ambil kecamatan yang valid (bukan "-" atau NaN)
        valid_kecamatans = df['KECAMATAN'].dropna()
        valid_kecamatans = valid_kecamatans[valid_kecamatans != '-']
        kecamatans_list = sorted(valid_kecamatans.unique())
        
        # Tambahkan opsi untuk data tanpa kecamatan
        kecamatan_options = ['[Tanpa Lokasi (Ghost/Prank)]'] + kecamatans_list
        
        if len(kecamatans_list) > 0:
            selected_kecamatans = st.sidebar.multiselect(
                "Pilih Kecamatan (opsional)", 
                kecamatan_options,
                default=[],  # Default kosong = tampilkan semua
                help="Pilih '[Tanpa Lokasi]' untuk ghost/prank, kosongkan untuk semua data"
            )
        else:
            selected_kecamatans = []
    else:
        selected_kecamatans = []
    
    # Apply filters
    df_filtered = df.copy()
    
    if selected_years:
        df_filtered = df_filtered[df_filtered['source'].isin(selected_years)]
    
    # Filter kategori
    if selected_categories and len(selected_categories) > 0:
        # Jika user pilih "[Tanpa Kategori]", ambil data dengan kategori "-"
        if '[Tanpa Kategori (Ghost/Prank)]' in selected_categories:
            # Ambil kategori normal yang dipilih
            normal_cats = [c for c in selected_categories if c != '[Tanpa Kategori (Ghost/Prank)]']
            # Filter: kategori "-" ATAU kategori yang dipilih
            df_filtered = df_filtered[
                (df_filtered['KATEGORI'].isin(['-', '']) | df_filtered['KATEGORI'].isna()) | 
                (df_filtered['KATEGORI'].isin(normal_cats))
            ]
        else:
            # Filter normal
            df_filtered = df_filtered[df_filtered['KATEGORI'].isin(selected_categories)]
    
    # Filter kecamatan
    if selected_kecamatans and len(selected_kecamatans) > 0:
        # Jika user pilih "[Tanpa Lokasi]", ambil data dengan kecamatan "-"
        if '[Tanpa Lokasi (Ghost/Prank)]' in selected_kecamatans:
            # Ambil kecamatan normal yang dipilih
            normal_kecs = [k for k in selected_kecamatans if k != '[Tanpa Lokasi (Ghost/Prank)]']
            # Filter: kecamatan "-" ATAU kecamatan yang dipilih
            df_filtered = df_filtered[
                (df_filtered['KECAMATAN'].isin(['-', '']) | df_filtered['KECAMATAN'].isna()) | 
                (df_filtered['KECAMATAN'].isin(normal_kecs))
            ]
        else:
            # Filter normal
            df_filtered = df_filtered[df_filtered['KECAMATAN'].isin(selected_kecamatans)]
    
    # Warning jika data kosong setelah filter
    if len(df_filtered) == 0:
        st.warning("⚠️ Tidak ada data yang sesuai dengan filter yang dipilih. Silakan ubah filter di sidebar.")
        return
    
    # Tabs untuk navigasi
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview", 
        "📈 Pola Waktu", 
        "📍 Analisis Lokasi", 
        "⚠️ Ghost & Prank Call",
        "👤 Analisis Agent"
    ])
    
    # ==================== TAB 1: OVERVIEW ====================
    with tab1:
        st.header("📊 Overview Data Call Center")
        
        # Key Metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Laporan", f"{len(df_filtered):,}")
        
        with col2:
            ghost_count = int(df_filtered['ghost_call'].sum())
            ghost_pct = (ghost_count / len(df_filtered) * 100) if len(df_filtered) > 0 else 0
            st.metric("Ghost Calls", f"{ghost_count:,}", f"{ghost_pct:.1f}%")
        
        with col3:
            prank_count = int(df_filtered['prank_call'].sum())
            prank_pct = (prank_count / len(df_filtered) * 100) if len(df_filtered) > 0 else 0
            st.metric("Prank Calls", f"{prank_count:,}", f"{prank_pct:.1f}%")
        
        with col4:
            short_count = int(df_filtered['short_call'].sum())
            short_pct = (short_count / len(df_filtered) * 100) if len(df_filtered) > 0 else 0
            st.metric("Short Calls (≤5s)", f"{short_count:,}", f"{short_pct:.1f}%")
        
        st.markdown("---")
        
        # Metrics tambahan
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            fake_loc_count = int(df_filtered['fake_location'].sum())
            fake_loc_pct = (fake_loc_count / len(df_filtered) * 100) if len(df_filtered) > 0 else 0
            st.metric("Lokasi Palsu", f"{fake_loc_count:,}", f"{fake_loc_pct:.1f}%")
        
        with col2:
            rapid_count = int(df_filtered['rapid_repeat'].sum())
            rapid_pct = (rapid_count / len(df_filtered) * 100) if len(df_filtered) > 0 else 0
            st.metric("Spam Berulang (<2 menit)", f"{rapid_count:,}", f"{rapid_pct:.1f}%")
        
        st.markdown("---")
        
        # Distribusi Kategori
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📋 Top 10 Kategori Laporan")
            if 'KATEGORI' in df_filtered.columns:
                category_counts = df_filtered['KATEGORI'].value_counts().head(10)
                
                if len(category_counts) > 0:
                    fig, ax = plt.subplots(figsize=(10, 6))
                    category_counts.plot(kind='barh', ax=ax, color='steelblue')
                    ax.set_xlabel('Jumlah Laporan')
                    ax.set_ylabel('Kategori')
                    ax.set_title('Top 10 Kategori Laporan')
                    plt.tight_layout()
                    st.pyplot(fig)
                else:
                    st.info("Tidak ada data kategori untuk ditampilkan.")
        
        with col2:
            st.subheader("📊 Top 10 Tipe Laporan")
            tipe_counts = df_filtered['TIPE LAPORAN'].value_counts().head(10)
            
            if len(tipe_counts) > 0:
                fig, ax = plt.subplots(figsize=(10, 6))
                colors = plt.cm.Set3(range(len(tipe_counts)))
                
                if len(tipe_counts) > 1:
                    ax.pie(tipe_counts.values, labels=tipe_counts.index, autopct='%1.1f%%', colors=colors)
                    ax.set_title('Top 10 Tipe Laporan')
                else:
                    tipe_counts.plot(kind='bar', ax=ax, color='steelblue')
                    ax.set_xlabel('Tipe Laporan')
                    ax.set_ylabel('Jumlah')
                    ax.set_title('Distribusi Tipe Laporan')
                
                st.pyplot(fig)
            else:
                st.info("Tidak ada data tipe laporan untuk ditampilkan.")
    
    # ==================== TAB 2: POLA WAKTU ====================
    with tab2:
        st.header("📈 Analisis Pola Waktu")
        
        # Pola Bulanan
        st.subheader("📅 Pola Bulanan (2024 vs 2025)")
        
        monthly_2024 = df[df['source'] == '2024']['ym'].value_counts().sort_index()
        monthly_2025 = df[df['source'] == '2025']['ym'].value_counts().sort_index()
        
        if len(monthly_2024) > 0 or len(monthly_2025) > 0:
            fig, ax = plt.subplots(figsize=(14, 6))
            if len(monthly_2024) > 0:
                ax.plot(monthly_2024.index.astype(str), monthly_2024.values, marker='o', label='2024', linewidth=2)
            if len(monthly_2025) > 0:
                ax.plot(monthly_2025.index.astype(str), monthly_2025.values, marker='o', label='2025', linewidth=2)
            ax.set_xlabel('Bulan')
            ax.set_ylabel('Jumlah Laporan')
            ax.set_title('Tren Laporan per Bulan (2024 vs 2025)')
            ax.legend()
            ax.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("Tidak ada data bulanan untuk ditampilkan.")
        
        st.markdown("---")
        
        # Pola Harian
        st.subheader("📆 Pola Harian")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Pola Harian 2024")
            daily_2024 = df[df['source'] == '2024']['date'].value_counts().sort_index()
            
            if len(daily_2024) > 0:
                fig, ax = plt.subplots(figsize=(12, 6))
                ax.plot(daily_2024.index, daily_2024.values, linewidth=1.5, color='coral')
                ax.set_xlabel('Tanggal')
                ax.set_ylabel('Jumlah Laporan')
                ax.set_title('Pola Harian Call Center 112 - Tahun 2024')
                ax.grid(True, alpha=0.3)
                plt.xticks(rotation=45)
                plt.tight_layout()
                st.pyplot(fig)
            else:
                st.info("Tidak ada data harian untuk 2024.")
        
        with col2:
            st.subheader("Pola Harian 2025")
            daily_2025 = df[df['source'] == '2025']['date'].value_counts().sort_index()
            
            if len(daily_2025) > 0:
                fig, ax = plt.subplots(figsize=(12, 6))
                ax.plot(daily_2025.index, daily_2025.values, linewidth=1.5, color='teal')
                ax.set_xlabel('Tanggal')
                ax.set_ylabel('Jumlah Laporan')
                ax.set_title('Pola Harian Call Center 112 - Tahun 2025')
                ax.grid(True, alpha=0.3)
                plt.xticks(rotation=45)
                plt.tight_layout()
                st.pyplot(fig)
            else:
                st.info("Tidak ada data harian untuk 2025.")
        
        st.markdown("---")
        
        # Pola Jam
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🕐 Pola Jam (2024)")
            hourly_2024 = df[df['source'] == '2024']['hour'].value_counts().sort_index()
            
            if len(hourly_2024) > 0:
                fig, ax = plt.subplots(figsize=(10, 6))
                ax.plot(hourly_2024.index, hourly_2024.values, marker='o', linewidth=2, color='coral')
                ax.set_xlabel('Jam (0-23)')
                ax.set_ylabel('Jumlah Laporan')
                ax.set_title('Pola Laporan per Jam - 2024')
                ax.grid(True, alpha=0.3)
                plt.tight_layout()
                st.pyplot(fig)
            else:
                st.info("Tidak ada data jam untuk 2024.")
        
        with col2:
            st.subheader("🕐 Pola Jam (2025)")
            hourly_2025 = df[df['source'] == '2025']['hour'].value_counts().sort_index()
            
            if len(hourly_2025) > 0:
                fig, ax = plt.subplots(figsize=(10, 6))
                ax.plot(hourly_2025.index, hourly_2025.values, marker='o', linewidth=2, color='teal')
                ax.set_xlabel('Jam (0-23)')
                ax.set_ylabel('Jumlah Laporan')
                ax.set_title('Pola Laporan per Jam - 2025')
                ax.grid(True, alpha=0.3)
                plt.tight_layout()
                st.pyplot(fig)
            else:
                st.info("Tidak ada data jam untuk 2025.")
        
        st.markdown("---")
        
        # Pola Hari dalam Seminggu
        st.subheader("📆 Pola Berdasarkan Hari dalam Seminggu")
        
        weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekday_counts = df_filtered['weekday'].value_counts().reindex(weekday_order)
        
        if len(weekday_counts.dropna()) > 0:
            fig, ax = plt.subplots(figsize=(12, 6))
            weekday_counts.plot(kind='bar', ax=ax, color='mediumpurple')
            ax.set_xlabel('Hari')
            ax.set_ylabel('Jumlah Laporan')
            ax.set_title('Distribusi Laporan Berdasarkan Hari dalam Seminggu')
            ax.set_xticklabels(weekday_counts.index, rotation=45)
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("Tidak ada data hari untuk ditampilkan.")
    
    # ==================== TAB 3: ANALISIS LOKASI ====================
    with tab3:
        st.header("📍 Analisis Berdasarkan Lokasi")
        
        if 'KECAMATAN' in df_filtered.columns:
            st.subheader("🗺️ Top 15 Kecamatan dengan Laporan Terbanyak")
            
            kecamatan_counts = df_filtered['KECAMATAN'].value_counts().head(15)
            
            if len(kecamatan_counts) > 0:
                fig, ax = plt.subplots(figsize=(12, 8))
                kecamatan_counts.plot(kind='barh', ax=ax, color='seagreen')
                ax.set_xlabel('Jumlah Laporan')
                ax.set_ylabel('Kecamatan')
                ax.set_title('Top 15 Kecamatan dengan Laporan Terbanyak')
                plt.tight_layout()
                st.pyplot(fig)
            else:
                st.info("Tidak ada data kecamatan untuk ditampilkan.")
            
            st.markdown("---")
            
            # Tabel Detail per Kecamatan - TAMPILKAN SEMUA (tidak tergantung filter)
            st.subheader("📋 Detail Laporan per Kecamatan (Top 20)")
            
            # Gunakan data ASLI (df), bukan df_filtered
            # Hanya ambil data dengan kecamatan valid (bukan "-" atau NaN)
            df_valid_kec = df[(df['KECAMATAN'].notna()) & (df['KECAMATAN'] != '-')].copy()
            
            if len(df_valid_kec) > 0:
                # Agregasi per kecamatan
                kecamatan_detail = df_valid_kec.groupby('KECAMATAN').agg({
                    'UID': 'count',
                    'ghost_call': lambda x: (x == True).sum(),  # Hitung True value
                    'prank_call': lambda x: (x == True).sum(),
                    'short_call': lambda x: (x == True).sum(),
                    'fake_location': lambda x: (x == True).sum()
                }).rename(columns={
                    'UID': 'Total Laporan',
                    'ghost_call': 'Ghost Calls',
                    'prank_call': 'Prank Calls',
                    'short_call': 'Short Calls',
                    'fake_location': 'Lokasi Palsu'
                }).sort_values('Total Laporan', ascending=False).head(20)
                
                # Convert to int untuk display yang lebih bersih
                kecamatan_detail = kecamatan_detail.astype(int)
                
                st.dataframe(kecamatan_detail, use_container_width=True)
                
                # Info tambahan
                st.info(f"ℹ️ **Catatan:** Tabel ini menampilkan data dari kecamatan yang memiliki lokasi valid. Ghost/Prank call ({int(df['ghost_call'].sum())} ghost + {int(df['prank_call'].sum())} prank) tidak memiliki data kecamatan sehingga tidak muncul di tabel ini.")
            else:
                st.info("Tidak ada data kecamatan yang valid.")
        
        st.markdown("---")
        
        # Analisis Lokasi Palsu Detail
        st.subheader("⚠️ Analisis Lokasi Palsu & Spam Berulang")
        
        col1, col2 = st.columns(2)
        
        with col1:
            fake_loc_count = int(df_filtered['fake_location'].sum())
            fake_loc_pct = (fake_loc_count / len(df_filtered) * 100) if len(df_filtered) > 0 else 0
            st.metric("Total Lokasi Palsu (Lat/Long = 0)", f"{fake_loc_count:,}", f"{fake_loc_pct:.2f}%")
            
            st.markdown("**Kemungkinan Penyebab:**")
            st.markdown("""
            - GPS pelapor tidak aktif
            - Panggilan dari telepon rumah/fixed line
            - Error sistem saat capture lokasi
            - Pelapor menolak akses lokasi
            """)
        
        with col2:
            rapid_count = int(df_filtered['rapid_repeat'].sum())
            rapid_pct = (rapid_count / len(df_filtered) * 100) if len(df_filtered) > 0 else 0
            st.metric("Spam Berulang (<2 menit)", f"{rapid_count:,}", f"{rapid_pct:.2f}%")
            
            st.markdown("**Kemungkinan Penyebab:**")
            st.markdown("""
            - Pelapor panic/frustrasi tidak terjawab
            - Prank caller yang persistent
            - Sistem auto-redial yang error
            - Testing sistem berulang
            """)
    
    # ==================== TAB 4: GHOST & PRANK CALL ====================
    with tab4:
        st.header("⚠️ Analisis Ghost Call & Prank Call")
        
        # Tren Ghost & Prank Call
        st.subheader("📉 Tren Ghost & Prank Call per Bulan")
        
        ghost_monthly = df[df['ghost_call']].groupby('ym').size()
        prank_monthly = df[df['prank_call']].groupby('ym').size()
        
        if len(ghost_monthly) > 0 or len(prank_monthly) > 0:
            fig, ax = plt.subplots(figsize=(14, 6))
            if len(ghost_monthly) > 0:
                ax.plot(ghost_monthly.index.astype(str), ghost_monthly.values, marker='o', label='Ghost Call', linewidth=2, color='red')
            if len(prank_monthly) > 0:
                ax.plot(prank_monthly.index.astype(str), prank_monthly.values, marker='o', label='Prank Call', linewidth=2, color='orange')
            ax.set_xlabel('Bulan')
            ax.set_ylabel('Jumlah Laporan')
            ax.set_title('Tren Ghost & Prank Call per Bulan (2024-2025)')
            ax.legend()
            ax.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("Tidak ada data ghost call atau prank call untuk ditampilkan.")
        
        st.markdown("---")
        
        # Insight & Rekomendasi
        st.subheader("💡 Insight & Rekomendasi")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**🔍 Kemungkinan Penyebab:**")
            st.markdown("""
            - **Ghost Call:**
              - Panggilan terputus otomatis sebelum terjawab
              - Masalah koneksi jaringan pelapor
              - Sistem auto-dial yang error
              - Pocket dial (panggilan tidak sengaja)
            
            - **Prank Call:**
              - Ketidaktahuan masyarakat tentang fungsi 112
              - Iseng/kurang kesadaran akan urgensi layanan
              - Testing sistem tanpa tujuan jelas
            """)
        
        with col2:
            st.markdown("**✅ Rekomendasi Solusi:**")
            st.markdown("""
            - **Edukasi & Sosialisasi:**
              - Kampanye media sosial tentang penggunaan 112
              - Kolaborasi dengan sekolah untuk edukasi dini
              
            - **Teknologi:**
              - Implementasi sistem deteksi pola panggilan berulang
              - Auto-blocking untuk nomor yang terdeteksi spam
              - Verifikasi lokasi GPS otomatis
              
            - **Operasional:**
              - Pelatihan agent untuk identifikasi cepat
              - SOP khusus penanganan ghost/prank call
              - Dashboard monitoring real-time
            """)
    
    # ==================== TAB 5: ANALISIS AGENT ====================
    with tab5:
        st.header("👤 Analisis Performa Agent")
        
        if 'AGENT L1' in df_filtered.columns:
            st.subheader("🏆 Top 15 Agent Berdasarkan Jumlah Laporan Ditangani")
            
            agent_counts = df_filtered['AGENT L1'].value_counts().head(15)
            
            if len(agent_counts) > 0:
                fig, ax = plt.subplots(figsize=(12, 8))
                agent_counts.plot(kind='barh', ax=ax, color='skyblue')
                ax.set_xlabel('Jumlah Laporan')
                ax.set_ylabel('Agent')
                ax.set_title('Top 15 Agent dengan Laporan Terbanyak')
                plt.tight_layout()
                st.pyplot(fig)
            else:
                st.info("Tidak ada data agent untuk ditampilkan.")
            
            st.markdown("---")
            
            # Ghost & Prank per Agent
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("👻 Top 10 Agent Penangan Ghost Call")
                ghost_df = df_filtered[df_filtered['ghost_call'] == True]
                
                if len(ghost_df) > 0:
                    ghost_by_agent = ghost_df['AGENT L1'].value_counts().head(10)
                    
                    if len(ghost_by_agent) > 0:
                        fig, ax = plt.subplots(figsize=(10, 6))
                        ghost_by_agent.plot(kind='bar', ax=ax, color='lightcoral')
                        ax.set_xlabel('Agent')
                        ax.set_ylabel('Jumlah Ghost Call')
                        ax.set_title('Top 10 Agent Penangan Ghost Call')
                        plt.xticks(rotation=45, ha='right')
                        plt.tight_layout()
                        st.pyplot(fig)
                    else:
                        st.info("Tidak ada data ghost call untuk agent.")
                else:
                    st.info("Tidak ada ghost call dalam data yang difilter.")
            
            with col2:
                st.subheader("🎭 Top 10 Agent Penangan Prank Call")
                prank_df = df_filtered[df_filtered['prank_call'] == True]
                
                if len(prank_df) > 0:
                    prank_by_agent = prank_df['AGENT L1'].value_counts().head(10)
                    
                    if len(prank_by_agent) > 0:
                        fig, ax = plt.subplots(figsize=(10, 6))
                        prank_by_agent.plot(kind='bar', ax=ax, color='lightsalmon')
                        ax.set_xlabel('Agent')
                        ax.set_ylabel('Jumlah Prank Call')
                        ax.set_title('Top 10 Agent Penangan Prank Call')
                        plt.xticks(rotation=45, ha='right')
                        plt.tight_layout()
                        st.pyplot(fig)
                    else:
                        st.info("Tidak ada data prank call untuk agent.")
                else:
                    st.info("Tidak ada prank call dalam data yang difilter.")
            
            st.markdown("---")
            
            # Tabel Detail Performa Agent
            st.subheader("📊 Detail Performa Agent")
            
            agent_detail = df_filtered.groupby('AGENT L1').agg({
                'UID': 'count',
                'ghost_call': 'sum',
                'prank_call': 'sum',
                'short_call': 'sum',
                'duration_seconds': 'mean'
            }).rename(columns={
                'UID': 'Total Laporan',
                'ghost_call': 'Ghost Calls',
                'prank_call': 'Prank Calls',
                'short_call': 'Short Calls',
                'duration_seconds': 'Rata-rata Durasi (detik)'
            }).sort_values('Total Laporan', ascending=False).head(20)
            
            # Convert to int kecuali durasi
            for col in ['Ghost Calls', 'Prank Calls', 'Short Calls']:
                agent_detail[col] = agent_detail[col].astype(int)
            
            # Format durasi
            agent_detail['Rata-rata Durasi (detik)'] = agent_detail['Rata-rata Durasi (detik)'].round(2)
            
            st.dataframe(agent_detail, use_container_width=True)
        else:
            st.warning("Kolom 'AGENT L1' tidak ditemukan dalam data.")

if __name__ == "__main__":
    main()

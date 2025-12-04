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
def parse_seconds(s):
    if pd.isna(s):
        return np.nan
    s = str(s)
    # Coba parsing format "0 Hari : 0 Jam : 0 Menit : 0 Detik"
    try:
        days = hours = mins = secs = 0
        m_days = re.search(r'(\d+)\s*Hari', s, flags=re.IGNORECASE)
        m_hours = re.search(r'(\d+)\s*Jam', s, flags=re.IGNORECASE)
        m_mins = re.search(r'(\d+)\s*Menit', s, flags=re.IGNORECASE)
        m_secs = re.search(r'(\d+)\s*Detik', s, flags=re.IGNORECASE)
        if m_days:
            days = int(m_days.group(1))
        if m_hours:
            hours = int(m_hours.group(1))
        if m_mins:
            mins = int(m_mins.group(1))
        if m_secs:
            secs = int(m_secs.group(1))
        if any([m_days, m_hours, m_mins, m_secs]):
            return secs + mins*60 + hours*3600 + days*86400
        nums = re.findall(r'(\d+)', s)
        if len(nums) >= 4:
            days, hours, mins, secs = map(int, nums[:4])
            return secs + mins*60 + hours*3600 + days*86400
        if nums:
            return int(nums[-1])
    except Exception:
        pass
    return np.nan

# robust helper to read excel trying engines
def read_excel_file(path):
    """Try to read excel using openpyxl first, fallback to pandas default"""
    try:
        return pd.read_excel(path, engine="openpyxl")
    except Exception as e1:
        try:
            return pd.read_excel(path)
        except Exception as e2:
            raise Exception(f"Failed to read '{path}'. Tries:\n - openpyxl error: {e1}\n - default engine error: {e2}")

# Cache data loading
@st.cache_data
def load_and_process_data(path_2024, path_2025):
    """Load dan preprocess data dari 2 file Excel (robust reading + cleaning)"""
    try:
        # Load data (robust)
        df24 = read_excel_file(path_2024)
        df25 = read_excel_file(path_2025)

        # Tambah kolom source
        df24['source'] = '2024'
        df25['source'] = '2025'

        # Gabung dataset
        df = pd.concat([df24, df25], ignore_index=True)

        # Bersihkan nama kolom (strip)
        df.columns = [c.strip() for c in df.columns]

        # Konversi waktu lapor ke datetime (jika ada)
        if 'WAKTU LAPOR' in df.columns:
            df['WAKTU LAPOR'] = pd.to_datetime(df['WAKTU LAPOR'], errors='coerce')
        else:
            df['WAKTU LAPOR'] = pd.NaT

        # Fitur turunan dari waktu (aman walau NaT)
        df['date'] = df['WAKTU LAPOR'].dt.date
        df['year'] = df['WAKTU LAPOR'].dt.year
        df['month'] = df['WAKTU LAPOR'].dt.month
        df['ym'] = df['WAKTU LAPOR'].dt.to_period('M')
        df['day'] = df['WAKTU LAPOR'].dt.day
        df['hour'] = df['WAKTU LAPOR'].dt.hour
        df['weekday'] = df['WAKTU LAPOR'].dt.day_name()

        # Parse durasi pengerjaan
        if 'DURASI PENGERJAAN' in df.columns:
            df['duration_seconds'] = df['DURASI PENGERJAAN'].apply(parse_seconds)
        else:
            df['duration_seconds'] = np.nan

        # Identifikasi short call (durasi <= 5 detik)
        df['short_call'] = (df['duration_seconds'] <= 5) & (df['duration_seconds'].notna())

        # Bersihkan tipe laporan (jaga string asli)
        if 'TIPE LAPORAN' in df.columns:
            df['TIPE LAPORAN'] = df['TIPE LAPORAN'].astype(str).str.strip()
        else:
            df['TIPE LAPORAN'] = 'unknown'

        # Cleaning kecamatan & kelurahan
        for c in ['KECAMATAN', 'KELURAHAN']:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip()
                df[c] = df[c].replace({'-': pd.NA, 'nan': pd.NA, '': pd.NA})
                df[c] = df[c].where(df[c].isna(), df[c].str.title())

        # --- force LAT/LONG numeric (very common source of bug) ---
        if 'LATITUDE' in df.columns:
            df['LATITUDE'] = pd.to_numeric(df['LATITUDE'], errors='coerce')
        if 'LONGITUDE' in df.columns:
            df['LONGITUDE'] = pd.to_numeric(df['LONGITUDE'], errors='coerce')

        # === DETEKSI GHOST CALL (LABEL + OTOMATIS) ===
        # label dari KATEGORI atau TIPE LAPORAN
        df['is_ghost_label'] = False
        if 'KATEGORI' in df.columns:
            df['is_ghost_label'] = df['KATEGORI'].astype(str).str.lower().str.contains('ghost', na=False)
        # juga cek TIPE LAPORAN (banyak sampelmu ghost ada di TIPE LAPORAN)
        if 'TIPE LAPORAN' in df.columns:
            df['is_ghost_label'] = df['is_ghost_label'] | df['TIPE LAPORAN'].astype(str).str.lower().str.contains('ghost', na=False)

        # Deteksi ghost call otomatis (robust)
        df['is_ghost_auto'] = False
        if all(col in df.columns for col in ['LATITUDE', 'LONGITUDE', 'DESKRIPSI']):
            df['DESKRIPSI'] = df['DESKRIPSI'].astype(str)
            df['is_ghost_auto'] = (
                (df['duration_seconds'].fillna(999999) == 0) &
                (df['DESKRIPSI'].fillna('').str.strip().str.len() < 5) &
                (df['LATITUDE'].fillna(0) == 0) &
                (df['LONGITUDE'].fillna(0) == 0)
            )

        # final ghost call = label agent (dari kategori/tipe) + deteksi otomatis
        df['ghost_call'] = df['is_ghost_label'] | df['is_ghost_auto']

        # === DETEKSI PRANK CALL ===
        # perhatikan sample: prank ada di TIPE LAPORAN; cek juga KATEGORI jika perlu
        df['prank_call'] = False
        if 'TIPE LAPORAN' in df.columns:
            df['prank_call'] = df['TIPE LAPORAN'].astype(str).str.lower().str.contains('prank', na=False)
        if 'KATEGORI' in df.columns:
            df['prank_call'] = df['prank_call'] | df['KATEGORI'].astype(str).str.lower().str.contains('prank', na=False)

        # === DETEKSI LOKASI PALSU ===
        df['fake_location'] = False
        if 'LATITUDE' in df.columns and 'LONGITUDE' in df.columns:
            df['fake_location'] = (df['LATITUDE'].fillna(0) == 0) & (df['LONGITUDE'].fillna(0) == 0)

        # === DETEKSI SPAM BERULANG ===
        df_sorted = df.sort_values('WAKTU LAPOR').copy()
        if 'UID' in df_sorted.columns:
            df_sorted['prev_time'] = df_sorted.groupby('UID')['WAKTU LAPOR'].shift(1)
            df_sorted['diff_min'] = (df_sorted['WAKTU LAPOR'] - df_sorted['prev_time']).dt.total_seconds() / 60
            df_sorted['rapid_repeat'] = df_sorted['diff_min'].fillna(99999) <= 2
        else:
            df_sorted['rapid_repeat'] = False

        # ensure boolean cols have no NaN and are bool type
        for col in ['is_ghost_label', 'is_ghost_auto', 'ghost_call', 'prank_call', 'fake_location', 'short_call', 'rapid_repeat']:
            if col in df_sorted.columns:
                df_sorted[col] = df_sorted[col].fillna(False).astype(bool)

        df = df_sorted.reset_index(drop=True)
        return df, None

    except FileNotFoundError as e:
        return None, f"File tidak ditemukan: {e}"
    except Exception as e:
        return None, f"Error saat memuat data: {e}"


# Main app
def main():
    st.title("📞 Dashboard Analisis Call Center 112")
    st.markdown("**Dashboard Interaktif untuk Mengeksplorasi Pola, Tren, dan Insight Data Laporan Call Center**")
    st.markdown("---")

    # Load data otomatis
    with st.spinner('⏳ Memuat dan memproses data...'):
        df, error = load_and_process_data(PATH_2024, PATH_2025)

    if error:
        st.error(f"❌ {error}")
        st.info("💡 **Cara memperbaiki:**\n1. Pastikan file Excel sudah ada di folder yang sama dengan file Python ini\n2. Atau ubah PATH_2024 dan PATH_2025 di awal file dengan path lengkap file kamu")
        return

    st.success(f"✅ Data berhasil dimuat! Total: {len(df):,} laporan")

    # Sidebar - Filters
    st.sidebar.header("🔍 Filter Data")

    # Filter tahun
    years = sorted(df['source'].dropna().unique())
    selected_years = st.sidebar.multiselect("Pilih Tahun", years, default=years)

    # Filter kategori
    if 'KATEGORI' in df.columns:
        categories = sorted(df['KATEGORI'].dropna().unique())
        selected_categories = st.sidebar.multiselect(
            "Pilih Kategori",
            categories,
            default=categories,
            help="Pilih satu atau lebih kategori"
        )
    else:
        selected_categories = []

    # Filter kecamatan
    if 'KECAMATAN' in df.columns:
        kecamatans = sorted(df['KECAMATAN'].dropna().unique())
        selected_kecamatans = st.sidebar.multiselect(
            "Pilih Kecamatan",
            kecamatans,
            default=kecamatans,
            help="Pilih satu atau lebih kecamatan"
        )
    else:
        selected_kecamatans = []

    # Apply filters
    df_filtered = df.copy()

    if selected_years:
        df_filtered = df_filtered[df_filtered['source'].isin(selected_years)]

    if selected_categories and 'KATEGORI' in df.columns:
        df_filtered = df_filtered[df_filtered['KATEGORI'].isin(selected_categories)]

    if selected_kecamatans and 'KECAMATAN' in df.columns:
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

        # Key Metrics (pakai df_filtered sehingga mengikuti filter)
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Laporan", f"{len(df_filtered):,}")

        with col2:
            ghost_count = int(df_filtered['ghost_call'].sum()) if 'ghost_call' in df_filtered.columns else 0
            ghost_pct = (ghost_count / len(df_filtered) * 100) if len(df_filtered) > 0 else 0
            st.metric("Ghost Calls", f"{ghost_count:,}", f"{ghost_pct:.1f}%")

        with col3:
            prank_count = int(df_filtered['prank_call'].sum()) if 'prank_call' in df_filtered.columns else 0
            prank_pct = (prank_count / len(df_filtered) * 100) if len(df_filtered) > 0 else 0
            st.metric("Prank Calls", f"{prank_count:,}", f"{prank_pct:.1f}%")

        with col4:
            short_count = int(df_filtered['short_call'].sum()) if 'short_call' in df_filtered.columns else 0
            short_pct = (short_count / len(df_filtered) * 100) if len(df_filtered) > 0 else 0
            st.metric("Short Calls (≤5s)", f"{short_count:,}", f"{short_pct:.1f}%")

        st.markdown("---")

        # Metrics tambahan untuk lokasi palsu dan spam
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            fake_loc_count = int(df_filtered['fake_location'].sum()) if 'fake_location' in df_filtered.columns else 0
            fake_loc_pct = (fake_loc_count / len(df_filtered) * 100) if len(df_filtered) > 0 else 0
            st.metric("Lokasi Palsu", f"{fake_loc_count:,}", f"{fake_loc_pct:.1f}%")

        with col2:
            rapid_count = int(df_filtered['rapid_repeat'].sum()) if 'rapid_repeat' in df_filtered.columns else 0
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
            tipe_counts = df_filtered['TIPE LAPORAN'].astype(str).value_counts().head(10)

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

        # Pola Bulanan (pakai df_filtered supaya ikut filter)
        st.subheader("📅 Pola Bulanan (2024 vs 2025)")

        monthly_2024 = df_filtered[df_filtered['source'] == '2024']['ym'].value_counts().sort_index()
        monthly_2025 = df_filtered[df_filtered['source'] == '2025']['ym'].value_counts().sort_index()

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

        # === POLA HARIAN ===
        st.subheader("📆 Pola Harian")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Pola Harian 2024")
            daily_2024 = df_filtered[df_filtered['source'] == '2024']['date'].value_counts().sort_index()

            if len(daily_2024) > 0:
                fig, ax = plt.subplots(figsize=(12, 6))
                ax.plot(daily_2024.index, daily_2024.values, linewidth=1.5)
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
            daily_2025 = df_filtered[df_filtered['source'] == '2025']['date'].value_counts().sort_index()

            if len(daily_2025) > 0:
                fig, ax = plt.subplots(figsize=(12, 6))
                ax.plot(daily_2025.index, daily_2025.values, linewidth=1.5)
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
            hourly_2024 = df_filtered[df_filtered['source'] == '2024']['hour'].value_counts().sort_index()

            if len(hourly_2024) > 0:
                fig, ax = plt.subplots(figsize=(10, 6))
                ax.plot(hourly_2024.index, hourly_2024.values, marker='o')
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
            hourly_2025 = df_filtered[df_filtered['source'] == '2025']['hour'].value_counts().sort_index()

            if len(hourly_2025) > 0:
                fig, ax = plt.subplots(figsize=(10, 6))
                ax.plot(hourly_2025.index, hourly_2025.values, marker='o')
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
            weekday_counts.plot(kind='bar', ax=ax)
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

            # Tabel Detail per Kecamatan
            st.subheader("📋 Detail Laporan per Kecamatan")
            kecamatan_detail = df_filtered.groupby('KECAMATAN').agg({
                'UID': 'count',
                'ghost_call': 'sum',
                'prank_call': 'sum',
                'short_call': 'sum',
                'fake_location': 'sum'
            }).rename(columns={
                'UID': 'Total Laporan',
                'ghost_call': 'Ghost Calls',
                'prank_call': 'Prank Calls',
                'short_call': 'Short Calls',
                'fake_location': 'Lokasi Palsu'
            }).sort_values('Total Laporan', ascending=False).head(20)

            st.dataframe(kecamatan_detail, width="stretch")

        st.markdown("---")

        # Analisis Lokasi Palsu Detail
        st.subheader("⚠️ Analisis Lokasi Palsu & Spam Berulang")

        col1, col2 = st.columns(2)

        with col1:
            fake_loc_count = int(df_filtered['fake_location'].sum()) if 'fake_location' in df_filtered.columns else 0
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
            rapid_count = int(df_filtered['rapid_repeat'].sum()) if 'rapid_repeat' in df_filtered.columns else 0
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

        # Tren Ghost & Prank Call (pakai df_filtered sehingga mengikuti filter)
        st.subheader("📉 Tren Ghost & Prank Call per Bulan")

        ghost_monthly = df_filtered[df_filtered['ghost_call']].groupby('ym').size() if 'ghost_call' in df_filtered.columns else pd.Series(dtype=int)
        prank_monthly = df_filtered[df_filtered['prank_call']].groupby('ym').size() if 'prank_call' in df_filtered.columns else pd.Series(dtype=int)

        if (len(ghost_monthly) > 0) or (len(prank_monthly) > 0):
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
              - SOP khusus penanganan ghost/prank call agar waktu respon tidak terbuang
              - Pencatatan terstruktur untuk nomor yang berpotensi spam
              - Koordinasi dengan operator seluler jika diperlukan
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

            # Ghost & Prank per Agent (pakai df_filtered agar mengikuti filter)
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("👻 Top 10 Agent Penangan Ghost Call")
                top_ghost_agent = (
                    df_filtered[df_filtered['ghost_call'] == True]
                    .groupby('AGENT L1')
                    .size()
                    .reset_index(name='jumlah')
                    .sort_values('jumlah', ascending=False)
                    .head(10)
                )
                if len(top_ghost_agent) > 0:
                    fig, ax = plt.subplots(figsize=(10, 6))
                    ax.bar(top_ghost_agent['AGENT L1'], top_ghost_agent['jumlah'])
                    ax.set_xlabel('Agent')
                    ax.set_ylabel('Jumlah Ghost Call')
                    ax.set_title('Top 10 Agent Penangan Ghost Call')
                    plt.xticks(rotation=45, ha='right')
                    plt.tight_layout()
                    st.pyplot(fig)
                    st.dataframe(top_ghost_agent.rename(columns={'AGENT L1': 'Agent'}), width="stretch")
                else:
                    st.info("Tidak ada data ghost call untuk agent.")

            with col2:
                st.subheader("😜 Top 10 Agent Penangan Prank Call")
                top_prank_agent = (
                    df_filtered[df_filtered['prank_call'] == True]
                    .groupby('AGENT L1')
                    .size()
                    .reset_index(name='jumlah')
                    .sort_values('jumlah', ascending=False)
                    .head(10)
                )
                if len(top_prank_agent) > 0:
                    fig, ax = plt.subplots(figsize=(10, 6))
                    ax.bar(top_prank_agent['AGENT L1'], top_prank_agent['jumlah'])
                    ax.set_xlabel('Agent')
                    ax.set_ylabel('Jumlah Prank Call')
                    ax.set_title('Top 10 Agent Penangan Prank Call')
                    plt.xticks(rotation=45, ha='right')
                    plt.tight_layout()
                    st.pyplot(fig)
                    st.dataframe(top_prank_agent.rename(columns={'AGENT L1': 'Agent'}), width="stretch")
                else:
                    st.info("Tidak ada data prank call untuk agent.")
        else:
            st.info("Data agent tidak tersedia dalam dataset.")

    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: gray;'>
    <p>Dashboard Call Center 112 | Intuisi dan Wawasan Data</p>
    <p>Developed with Streamlit 🎈</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()

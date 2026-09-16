import unittest

from manga_checker.privilege import STATUS_NO, STATUS_UNKNOWN, STATUS_YES, evaluate_privilege


class PrivilegeEvalTests(unittest.TestCase):
    def test_confirmed_on_matching_product_card(self) -> None:
        html = """
        <aside class="side">特典あり アニメイト特典 魔都精兵のスレイブ</aside>
        <ul class="item_list">
          <li class="item"><p class="item_name">夜は猫といっしょ</p>
            <span>アニメイト特典 描き下ろしイラストカード</span></li>
        </ul>
        """
        status, _ = evaluate_privilege(
            html,
            title_for_match="夜は猫といっしょ",
            source_url="https://www.animate-onlineshop.jp/products/list.php",
        )
        self.assertEqual(status, STATUS_YES)

    def test_banner_and_sidebar_are_ignored(self) -> None:
        html = """
        <div class="recommend banner">魔都精兵のスレイブ 特典あり アニメイト特典</div>
        <aside class="sidebar"><label><input type="checkbox">特典あり</label></aside>
        <p class="note">最新の特典取り扱い状況につきましては商品詳細をご確認ください。特典あり</p>
        <ul class="item_list">
          <li class="item"><p class="item_name">夜は猫といっしょ</p><span>在庫あり 720円</span></li>
        </ul>
        """
        status, _ = evaluate_privilege(
            html,
            title_for_match="夜は猫といっしょ",
            source_url="https://www.animate-onlineshop.jp/products/list.php",
        )
        self.assertEqual(status, STATUS_NO)

    def test_melonbooks_limited_badge_and_leaflet(self) -> None:
        html = """
        <div class="product_list">
          <div class="product">
            <a class="title">初凪ヒメリウム</a>
            <img alt="メロン限定版" title="特典">
            <span class="tokuten">特典（描き下ろし4Pリーフレット）</span>
          </div>
        </div>
        """
        status, detail = evaluate_privilege(
            html,
            title_for_match="初凪ヒメリウム",
            source_url="https://www.melonbooks.co.jp/search/search.php",
        )
        self.assertEqual(status, STATUS_UNKNOWN)
        self.assertIn("詳細", detail)

    def test_gamers_g_privilege_icon(self) -> None:
        html = """
        <ul class="item_list">
          <li class="item">
            <p class="item_name">初凪ヒメリウム</p>
            <span class="icon_present"></span>
          </li>
        </ul>
        """
        status, detail = evaluate_privilege(
            html,
            title_for_match="初凪ヒメリウム",
            source_url="https://www.gamers.co.jp/products/list.php",
        )
        self.assertEqual(status, STATUS_YES)
        self.assertTrue("G特典" in detail or "icon_present" in detail)

    def test_melonbooks_icon_and_acrylic_band(self) -> None:
        html = """
        <div class="item_list">
          <div class="item">
            <a class="title">初凪ヒメリウム</a>
            <span class="icon_tokuten campaign_band"></span>
            <img class="label_gentei" alt="">
            <p class="band">アクリルスタンド</p>
          </div>
        </div>
        """
        status, detail = evaluate_privilege(
            html,
            title_for_match="初凪ヒメリウム",
            source_url="https://www.melonbooks.co.jp/search/search.php",
        )
        self.assertEqual(status, STATUS_UNKNOWN)
        self.assertIn("詳細", detail)

    def test_melonbooks_text_keywords(self) -> None:
        html = """
        <div class="item_list">
          <div class="item">
            <p class="title">初凪ヒメリウム</p>
            <p>メロン限定版 描き下ろしリーフレット</p>
          </div>
        </div>
        """
        status, detail = evaluate_privilege(
            html,
            title_for_match="初凪ヒメリウム",
            source_url="https://www.melonbooks.co.jp/search/search.php",
        )
        self.assertEqual(status, STATUS_UNKNOWN, detail)

    def test_melonbooks_class_only_icon_is_ignored(self) -> None:
        html = """
        <div class="item_list">
          <div class="item">
            <span class="icon_tokuten"></span>
            <p class="title">初凪ヒメリウム</p>
            <span>在庫あり 726円</span>
          </div>
        </div>
        """
        status, _ = evaluate_privilege(
            html,
            title_for_match="初凪ヒメリウム",
            source_url="https://www.melonbooks.co.jp/search/search.php",
        )
        self.assertEqual(status, STATUS_UNKNOWN)

    def test_kinokuniya_ignores_store_disclaimer(self) -> None:
        html = """
        <h1>初凪ヒメリウム</h1>
        <p class="note">店舗限定の特典はお付けできません。オンラインでは特典をお付けできません。</p>
        <div>在庫あり 726円</div>
        """
        status, detail = evaluate_privilege(
            html,
            title_for_match="初凪ヒメリウム",
            source_url="https://www.kinokuniya.co.jp/f/dsg-01-9784000000000",
            store_id="kinokuniya",
        )
        self.assertEqual(status, STATUS_NO, detail)

    def test_kinokuniya_ignores_header_member_perks(self) -> None:
        html = """
        <header>会員特典 ポイント特典 店舗受取特典</header>
        <footer>ポイント特典のご案内</footer>
        <h3>初凪ヒメリウム</h3>
        <p>店舗限定の特典はお付けできません。</p>
        """
        status, detail = evaluate_privilege(
            html,
            title_for_match="初凪ヒメリウム",
            source_url="https://www.kinokuniya.co.jp/disp/CSfDispListPage_001.jsp",
            store_id="kinokuniya",
        )
        self.assertEqual(status, STATUS_NO, detail)

    def test_kinokuniya_title_privilege(self) -> None:
        html = """
        <header>会員特典 ポイント特典</header>
        <h1>初凪ヒメリウム 特典ペーパー付き</h1>
        <p class="note">店舗限定の特典はお付けできません。</p>
        """
        status, detail = evaluate_privilege(
            html,
            title_for_match="初凪ヒメリウム",
            source_url="https://www.kinokuniya.co.jp/f/dsg-01-9784000000000",
            store_id="kinokuniya",
        )
        self.assertEqual(status, STATUS_YES, detail)

    def test_zero_results(self) -> None:
        status, _ = evaluate_privilege(
            "検索結果 0件 該当する商品はございません",
            title_for_match="存在しない作品",
            source_url="https://www.animate-onlineshop.jp/products/list.php",
        )
        self.assertEqual(status, STATUS_UNKNOWN)

    def test_ten_hits_without_privilege_is_no_not_unknown(self) -> None:
        html = """
        <p>検索結果 10件</p>
        <ul class="item_list">
          <li class="item"><p class="item_name">初凪ヒメリウム</p><span>在庫あり 770円</span></li>
        </ul>
        """
        status, detail = evaluate_privilege(
            html,
            title_for_match="初凪ヒメリウム",
            source_url="https://www.gamers.co.jp/products/list.php",
        )
        self.assertEqual(status, STATUS_NO, detail)

    def test_kinokuniya_product_without_privilege_is_no(self) -> None:
        html = """
        <p>検索結果 20件</p>
        <h1>初凪ヒメリウム 1</h1>
        <p>在庫あり</p>
        """
        status, detail = evaluate_privilege(
            html,
            title_for_match="初凪ヒメリウム",
            source_url="https://www.kinokuniya.co.jp/f/dsg-01-9784000000000",
            store_id="kinokuniya",
        )
        self.assertEqual(status, STATUS_NO, detail)

    def test_short_title_ignores_different_work(self) -> None:
        html = """
        <ul class="item_list">
          <li class="item"><p class="item_name">裏切り者のラブソング</p>
            <span>アニメイト特典 描き下ろし</span></li>
        </ul>
        """
        status, _ = evaluate_privilege(
            html,
            title_for_match="ラブソング",
            author="別の人",
            source_url="https://www.animate-onlineshop.jp/products/list.php",
        )
        self.assertEqual(status, STATUS_NO)

    def test_short_title_matches_own_card(self) -> None:
        html = """
        <ul class="item_list">
          <li class="item"><p class="item_name">ラブソング</p>
            <span>アニメイト特典 描き下ろし</span></li>
        </ul>
        """
        status, _ = evaluate_privilege(
            html,
            title_for_match="ラブソング",
            source_url="https://www.animate-onlineshop.jp/products/list.php",
        )
        self.assertEqual(status, STATUS_YES)


class MelonDetailTests(unittest.TestCase):
    def test_first_detail_url_prefers_matching_title(self) -> None:
        from manga_checker.melon import first_melon_detail_url

        html = """
        <ul class="item_list">
          <li class="item"><a href="/detail/detail.php?product_id=111">別作品</a></li>
          <li class="item"><a href="/detail/detail.php?product_id=222">初凪ヒメリウム</a></li>
        </ul>
        """
        url = first_melon_detail_url(
            html,
            "https://www.melonbooks.co.jp/search/search.php",
            "初凪ヒメリウム",
        )
        self.assertIn("product_id=222", url)

    def test_first_detail_url_rejects_unrelated_first_hit(self) -> None:
        from manga_checker.melon import first_melon_detail_url

        html = """
        <ul class="item_list">
          <li class="item"><a href="/detail/detail.php?product_id=111">ひと夏limited</a></li>
        </ul>
        """
        url = first_melon_detail_url(
            html,
            "https://www.melonbooks.co.jp/search/search.php",
            "ヒトナー",
        )
        self.assertEqual(url, "")

    def test_first_detail_url_accepts_id_query(self) -> None:
        from manga_checker.melon import first_melon_detail_url

        html = """
        <ul class="item_list">
          <li class="item"><a href="/detail/detail.php?id=222">初凪ヒメリウム</a></li>
        </ul>
        """
        url = first_melon_detail_url(
            html,
            "https://www.melonbooks.co.jp/search/search.php",
            "初凪ヒメリウム",
        )
        self.assertIn("product_id=222", url)

    def test_first_detail_url_accepts_isbn_on_card(self) -> None:
        from manga_checker.melon import first_melon_detail_url

        html = """
        <ul class="item_list">
          <li class="item"><a href="/detail/detail.php?product_id=111">ひと夏limited</a></li>
          <li class="item"><a href="/detail/detail.php?product_id=222">商品
            ISBN:9784088852317</a></li>
        </ul>
        """
        url = first_melon_detail_url(
            html,
            "https://www.melonbooks.co.jp/search/search.php",
            "ヒトナー",
            "9784088852317",
        )
        self.assertIn("product_id=222", url)

    def test_detail_privilege_box(self) -> None:
        from manga_checker.melon import evaluate_melon_detail

        html = """
        <h1>初凪ヒメリウム</h1>
        <div class="privilege_box"><h2>特典情報</h2><p>描き下ろし</p></div>
        """
        status, detail = evaluate_melon_detail(html)
        self.assertEqual(status, STATUS_YES)
        self.assertIn("特典", detail)

    def test_detail_melonbooks_text(self) -> None:
        from manga_checker.melon import evaluate_melon_detail

        html = "<div>商品説明 メロンブックス特典 ペーパー付き</div>"
        status, detail = evaluate_melon_detail(html)
        self.assertEqual(status, STATUS_YES)
        self.assertIn("メロンブックス特典", detail)

    def test_detail_heading_and_illustration_card(self) -> None:
        from manga_checker.melon import evaluate_melon_detail

        html = """
        <div class="item_detail">
          <h2>特典情報</h2>
          <p>描き下ろしイラストカード</p>
        </div>
        """
        status, detail = evaluate_melon_detail(html)
        self.assertEqual(status, STATUS_YES)
        self.assertTrue("特典情報" in detail or "イラストカード" in detail)

    def test_detail_privilege_class_block(self) -> None:
        from manga_checker.melon import evaluate_melon_detail

        html = '<section class="privilege"><h3>特典情報</h3><p>イラストカード</p></section>'
        status, detail = evaluate_melon_detail(html)
        self.assertEqual(status, STATUS_YES)
        self.assertIn("特典", detail)

    def test_detail_without_privilege(self) -> None:
        from manga_checker.melon import evaluate_melon_detail

        html = "<h1>初凪ヒメリウム</h1><p>在庫あり 726円</p>"
        status, _ = evaluate_melon_detail(html)
        self.assertEqual(status, STATUS_NO)

    def test_detail_ignores_related_label_works(self) -> None:
        from manga_checker.melon import evaluate_melon_detail

        html = """
        <div id="contents">
          <div class="item_detail">
            <h1>息子の彼女 1</h1>
            <table class="spec">
              <tr><th>仕様</th><td>B6判</td></tr>
            </table>
            <p>在庫あり 726円</p>
          </div>
          <div class="recommend" id="related">
            <h2>このレーベルの他の作品</h2>
            <div class="carousel">
              <a href="/detail/detail.php?product_id=999">だれでも抱けるキミが好き
              描き下ろしイラストカード</a>
            </div>
          </div>
        </div>
        """
        status, _ = evaluate_melon_detail(html)
        self.assertEqual(status, STATUS_NO)

    def test_detail_ignores_related_heading_without_class(self) -> None:
        from manga_checker.melon import evaluate_melon_detail

        html = """
        <div class="item_detail">
          <h1>息子の彼女 1</h1>
          <p>在庫あり</p>
          <h2>このレーベルの他の作品</h2>
          <div class="item">だれでも抱けるキミが好き 描き下ろしイラストカード</div>
        </div>
        """
        status, _ = evaluate_melon_detail(html)
        self.assertEqual(status, STATUS_NO)

    def test_detail_ignores_ended_and_chrome_header(self) -> None:
        from manga_checker.melon import evaluate_melon_detail

        html = """
        <header><a href="/products/privilege_list.php">限定版・特典</a></header>
        <nav>特典取り扱いについて</nav>
        <h1>初凪ヒメリウム</h1>
        <div class="privilege"><h2>特典情報</h2><p>※特典は終了しました</p></div>
        <p>在庫あり 726円</p>
        """
        status, _ = evaluate_melon_detail(html)
        self.assertEqual(status, STATUS_NO)

    def test_listing_ignores_generic_tokuten_word(self) -> None:
        html = """
        <div class="item_list">
          <div class="item">
            <p class="title">初凪ヒメリウム</p>
            <p>※特典は終了しました。限定版・特典の案内はヘッダーから</p>
          </div>
        </div>
        """
        status, _ = evaluate_privilege(
            html,
            title_for_match="初凪ヒメリウム",
            source_url="https://www.melonbooks.co.jp/search/search.php",
        )
        self.assertEqual(status, STATUS_UNKNOWN)


class AnimateDetailTests(unittest.TestCase):
    def test_first_pd_url_prefers_matching_title(self) -> None:
        from manga_checker.animate import first_animate_detail_url

        html = """
        <ul class="item_list">
          <li class="item"><a href="/pd/111/">別作品</a></li>
          <li class="item"><a href="/pd/222/">初凪ヒメリウム (1)</a></li>
        </ul>
        """
        url = first_animate_detail_url(
            html,
            "https://www.animate-onlineshop.jp/products/list.php",
            "初凪ヒメリウム",
        )
        self.assertEqual(url, "https://www.animate-onlineshop.jp/pd/222/")

    def test_first_pd_url_rejects_unrelated_first_hit(self) -> None:
        from manga_checker.animate import first_animate_detail_url

        html = """
        <ul class="item_list">
          <li class="item"><a href="/pd/111/">ひと夏limited</a></li>
        </ul>
        """
        url = first_animate_detail_url(
            html,
            "https://www.animate-onlineshop.jp/products/list.php",
            "ヒトナー",
        )
        self.assertEqual(url, "")

    def test_isbn_search_returns_first_pd_even_without_title_match(self) -> None:
        from manga_checker.animate import first_animate_detail_url

        html = """
        <ul class="item_list">
          <li class="item"><a href="/pd/111/">ひと夏limited</a></li>
        </ul>
        """
        url = first_animate_detail_url(
            html,
            "https://www.animate-onlineshop.jp/products/list.php",
            "ヒトナー",
            isbn="9784088852317",
        )
        self.assertEqual(url, "https://www.animate-onlineshop.jp/pd/111/")

    def test_tokuten_block_and_heading(self) -> None:
        from manga_checker.animate import evaluate_animate_detail

        html = """
        <div id="tokuten">
          <h2>特典について</h2>
          <p>アニメイト特典：描き下ろしイラストカード</p>
        </div>
        """
        status, detail = evaluate_animate_detail(html)
        self.assertEqual(status, STATUS_YES)
        self.assertTrue("特典について" in detail or "アニメイト特典" in detail)

    def test_detail_without_privilege(self) -> None:
        from manga_checker.animate import evaluate_animate_detail

        html = "<h1>初凪ヒメリウム</h1><p>在庫あり 726円</p>"
        status, _ = evaluate_animate_detail(html)
        self.assertEqual(status, STATUS_NO)


class ToranoanaDetailTests(unittest.TestCase):
    def test_first_item_url_prefers_matching_title(self) -> None:
        from manga_checker.toranoana import first_toranoana_detail_url

        html = """
        <ul class="product-list-container">
          <li class="product-list-item"><a href="/tora/ec/item/111/">別作品</a></li>
          <li class="product-list-item"><a href="/tora/ec/item/222/">初凪ヒメリウム 1</a></li>
        </ul>
        """
        url = first_toranoana_detail_url(
            html,
            "https://ecs.toranoana.jp/tora/ec/app/catalog/list/",
            "初凪ヒメリウム",
        )
        self.assertEqual(url, "https://ecs.toranoana.jp/tora/ec/item/222/")

    def test_first_item_url_rejects_unrelated_first_hit(self) -> None:
        from manga_checker.toranoana import first_toranoana_detail_url

        html = """
        <li class="product-list-item"><a href="/tora/ec/item/111/">ひと夏limited</a></li>
        """
        url = first_toranoana_detail_url(
            html,
            "https://ecs.toranoana.jp/tora/ec/app/catalog/list/",
            "ヒトナー",
        )
        self.assertEqual(url, "")

    def test_detail_privilege_info(self) -> None:
        from manga_checker.toranoana import evaluate_toranoana_detail

        html = """
        <section class="product-detail">
          <h1>ヒトナー 1</h1>
          <div class="privilege-info">とらのあな特典 描き下ろし</div>
        </section>
        """
        status, detail = evaluate_toranoana_detail(html)
        self.assertEqual(status, STATUS_YES)
        self.assertIn("とらのあな特典", detail)

    def test_floating_banner_is_ignored(self) -> None:
        from manga_checker.toranoana import evaluate_toranoana_detail

        html = """
        <section class="product-detail"><h1>ヒトナー 1</h1></section>
        <div id="js-benefit-floating" class="p-benefit-floating">
          <div class="p-benefit-floating-title">特典つきます！</div>
        </div>
        <div class="privilege-info"></div>
        """
        status, _ = evaluate_toranoana_detail(html)
        self.assertEqual(status, STATUS_NO)
